// Ticket system for tracking purchases, line snapshots, and refund eligibility
// Uses Upstash Redis to match existing project patterns

import { Redis } from '@upstash/redis'

function getRedis(): Redis {
  const url = (process.env.UPSTASH_REDIS_REST_URL || '').trim()
  const token = (process.env.UPSTASH_REDIS_REST_TOKEN || '').trim()
  if (!url || !token) throw new Error('Upstash Redis not configured')
  return new Redis({ url, token })
}

// ─── Types ───

export interface TicketLeg {
  game_id: string
  team: string
  spread_at_purchase: number | null // actual line: spread point (+3.5), total line (220.5), or null for ML
  bet_type: string // spread, moneyline, total, etc.
  odds: string | number | null // American odds (-110, +150)
  sport: string
  home_team: string
  away_team: string
  result: 'win' | 'loss' | 'push' | null
  covered: boolean | null
}

export interface Ticket {
  id: string
  user_id: string // email
  purchase_time: string
  pack_type: string // tier id: single, 2leg, 3leg, etc.
  stripe_payment_intent_id: string
  legs: TicketLeg[]
  refund_eligible: boolean | null // auto-calculated
  refund_status: 'pending' | 'approved' | 'denied'
  admin_override: boolean
  created_at: string
  scored_at: string | null
}

// ─── Counter for auto-increment IDs ───

async function nextTicketId(): Promise<string> {
  const r = getRedis()
  const id = await r.incr('tickets:counter')
  return id.toString()
}

// ─── CRUD ───

export async function createTicket(data: {
  user_id: string
  pack_type: string
  stripe_payment_intent_id: string
  legs: TicketLeg[]
}): Promise<Ticket> {
  const r = getRedis()
  const id = await nextTicketId()
  const now = new Date().toISOString()

  const ticket: Ticket = {
    id,
    user_id: data.user_id,
    purchase_time: now,
    pack_type: data.pack_type,
    stripe_payment_intent_id: data.stripe_payment_intent_id,
    legs: data.legs,
    refund_eligible: null,
    refund_status: 'pending',
    admin_override: false,
    created_at: now,
    scored_at: null,
  }

  await r.set(`ticket:${id}`, ticket)
  // Index by time (for listing) and by user
  await r.zadd('tickets:all', { score: Date.now(), member: id })
  await r.zadd(`tickets:user:${data.user_id.toLowerCase()}`, { score: Date.now(), member: id })

  return ticket
}

export async function getTicket(id: string): Promise<Ticket | null> {
  const r = getRedis()
  return await r.get<Ticket>(`ticket:${id}`)
}

export async function updateTicket(id: string, updates: Partial<Ticket>): Promise<Ticket | null> {
  const r = getRedis()
  const ticket = await r.get<Ticket>(`ticket:${id}`)
  if (!ticket) return null

  const updated = { ...ticket, ...updates }
  await r.set(`ticket:${id}`, updated)
  return updated
}

export async function listTickets(opts?: {
  limit?: number
  offset?: number
  pack_type?: string
  refund_status?: string
  date_from?: string
  date_to?: string
}): Promise<{ tickets: Ticket[]; total: number }> {
  const r = getRedis()
  const limit = opts?.limit || 100
  const offset = opts?.offset || 0

  // Get all ticket IDs (newest first)
  const total = await r.zcard('tickets:all')
  const ids = await r.zrange('tickets:all', 0, -1, { rev: true }) as string[]

  // Fetch all tickets (in production you'd paginate better)
  const tickets: Ticket[] = []
  for (const id of ids) {
    const ticket = await r.get<Ticket>(`ticket:${id}`)
    if (!ticket) continue

    // Apply filters
    if (opts?.pack_type && ticket.pack_type !== opts.pack_type) continue
    if (opts?.refund_status && ticket.refund_status !== opts.refund_status) continue
    if (opts?.date_from && ticket.purchase_time < opts.date_from) continue
    if (opts?.date_to && ticket.purchase_time > opts.date_to + 'T23:59:59') continue

    tickets.push(ticket)
  }

  return {
    tickets: tickets.slice(offset, offset + limit),
    total: tickets.length,
  }
}

// ─── Refund Eligibility Calculation ───

export function calculateRefundEligibility(ticket: Ticket): boolean | null {
  const legs = ticket.legs
  const allScored = legs.every(l => l.covered !== null)
  if (!allScored) return null // Not all results in yet

  const tier = ticket.pack_type

  // For all parlay tiers: refund if ANY leg loses
  // (This matches the guarantee: "Any leg loses? Full refund.")
  const lostLegs = legs.filter(l => l.covered === false)

  switch (tier) {
    case 'single':
      // Single pick: refund if it loses
      return lostLegs.length > 0

    case '2leg':
      // 2-leg: refund if ANY leg loses (current guarantee)
      return lostLegs.length > 0

    default:
      // All other parlays (3leg-7leg): refund if ANY leg loses
      return lostLegs.length > 0
  }
}

// ─── Score tickets against results ───

export async function scoreTicket(
  ticketId: string,
  results: Record<string, { winner: string; home_score?: number; away_score?: number; margin?: number }>
): Promise<Ticket | null> {
  const ticket = await getTicket(ticketId)
  if (!ticket) return null

  const updatedLegs = ticket.legs.map(leg => {
    const gameResult = results[leg.game_id]
    if (!gameResult) return leg // No result yet

    // Determine if the pick covered using the ticket's own stamped line
    let covered: boolean
    if (leg.bet_type === 'spread' && leg.spread_at_purchase != null) {
      // Spread bet: check if team covered the spread at purchase
      const spread = typeof leg.spread_at_purchase === 'number'
        ? leg.spread_at_purchase
        : parseFloat(String(leg.spread_at_purchase))
      const margin = gameResult.margin || 0
      covered = margin + spread > 0
    } else if (leg.bet_type === 'total' && leg.spread_at_purchase != null) {
      // Total bet: spread_at_purchase holds the O/U line at purchase
      const line = typeof leg.spread_at_purchase === 'number'
        ? leg.spread_at_purchase
        : parseFloat(String(leg.spread_at_purchase))
      const totalScore = (gameResult.home_score || 0) + (gameResult.away_score || 0)
      const isOver = leg.team.includes('Over') || leg.team.toLowerCase().includes('over')
      if (totalScore === line) {
        // Push
        return { ...leg, result: 'push' as const, covered: null }
      }
      covered = isOver ? totalScore > line : totalScore < line
    } else {
      // Moneyline: did the team win?
      covered = gameResult.winner === leg.team
    }

    return {
      ...leg,
      result: covered ? 'win' as const : 'loss' as const,
      covered,
    }
  })

  const updatedTicket: Partial<Ticket> = {
    legs: updatedLegs,
    scored_at: new Date().toISOString(),
  }

  // Calculate refund eligibility
  const tempTicket = { ...ticket, legs: updatedLegs }
  updatedTicket.refund_eligible = calculateRefundEligibility(tempTicket)

  return await updateTicket(ticketId, updatedTicket)
}

// ─── Get unscored tickets ───

export async function getUnscoredTickets(): Promise<Ticket[]> {
  const { tickets } = await listTickets({ limit: 500 })
  return tickets.filter(t => t.scored_at === null || t.legs.some(l => l.covered === null))
}

// ─── Admin: approve/deny refund ───

export async function setRefundStatus(
  ticketId: string,
  status: 'approved' | 'denied'
): Promise<Ticket | null> {
  return await updateTicket(ticketId, {
    refund_status: status,
    admin_override: true,
  })
}
