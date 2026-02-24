import { NextRequest, NextResponse } from 'next/server'
import Stripe from 'stripe'
import jwt from 'jsonwebtoken'
import { promises as fs } from 'fs'
import path from 'path'
import crypto from 'crypto'
import { getTierConfig } from '../../../lib/tier-config'
import { canUserPurchase, getUserDailyPickIds } from '../../../lib/purchase-tracker'
import { getClient } from '../../../../engine/db'

const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-here'
const ANALYZED_GAMES_FILE = path.join(process.cwd(), 'engine', 'analyzed_games.json')

function getStripe() {
  return new Stripe((process.env.STRIPE_SECRET_KEY || '').trim(), {
    apiVersion: '2025-02-24.acacia',
  })
}

// ─── Fetch analyzed games from our engine (Turso primary, local JSON fallback) ───
async function fetchAnalyzedGames(pickDate: string): Promise<any[]> {
  // Try Turso first
  try {
    const client = getClient()
    const result = await client.execute({
      sql: 'SELECT * FROM daily_picks WHERE pick_date = ?',
      args: [pickDate],
    })
    if (result.rows && result.rows.length > 0) {
      return result.rows.map((row: any) => {
        if (row.raw_json) {
          try { return JSON.parse(row.raw_json) } catch {}
        }
        return {
          sport: row.sport, home: row.home, away: row.away,
          spread: row.spread, spread_str: row.spread_str,
          pick: row.pick, cover_prob: row.cover_prob,
          enhanced_prob: row.enhanced_prob,
          ml_pick: row.ml_pick, ml_prob: row.ml_prob,
          total_line: row.total_line, ou_pick: row.ou_pick, ou_prob: row.ou_prob,
          upset_score: row.upset_score, upset_flip: row.upset_flip === 1,
          game_time: row.game_time, commence_time: row.commence_time,
          book_count: row.book_count, game_date: row.pick_date,
        }
      })
    }
  } catch (e) {
    console.error('Turso fetch failed:', e)
  }
  // Fallback to local JSON
  try {
    const raw = await fs.readFile(ANALYZED_GAMES_FILE, 'utf-8')
    return JSON.parse(raw)
  } catch {
    return []
  }
}

// ─── Filter to games that haven't started yet (60-min buffer) ───
function isGameEligible(game: any): boolean {
  const ct = game.commence_time
  if (!ct) return true
  const start = new Date(ct)
  if (isNaN(start.getTime())) return true
  return start > new Date(Date.now() + 60 * 60_000)
}

// ─── Seeded PRNG for per-user deterministic parlays ───
function mulberry32(seed: number) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = t + Math.imul(t ^ (t >>> 7), 61 | t) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function userSeed(email: string, dateStr: string, purchaseNum: number = 0): number {
  const raw = `${email}:${dateStr}:${purchaseNum}:checkout:parlayguarantee`
  const hash = crypto.createHash('sha256').update(raw).digest('hex')
  return parseInt(hash.slice(0, 10), 16)
}

// ─── Build a parlay from our engine's analyzed games ───
function buildParlayFromEngine(
  games: any[],
  numLegs: number,
  email: string,
  dateStr: string,
  purchaseCount: number = 0,
  sportFilter?: string,
  betType?: 'moneyline' | 'spread',
  excludePickIds: string[] = [],
): any | null {
  // Filter eligible future games
  let pool = games.filter(isGameEligible)

  // Sport filter
  if (sportFilter) {
    const sf = sportFilter.toLowerCase()
    const sportPool = pool.filter(g => {
      const s = (g.sport || '').toLowerCase()
      if (sf === 'nba') return s.includes('nba')
      if (sf === 'ncaab') return s.includes('ncaa') || s.includes('cbb') || s.includes('college')
      return s.includes(sf)
    })
    if (sportPool.length >= numLegs) pool = sportPool
  }

  // Exclude already-purchased picks
  pool = pool.filter(g => {
    const pickId = `${g.home}_${g.away}_${g.game_date}`
    return !excludePickIds.includes(pickId)
  })

  if (pool.length < numLegs) return null

  // Sort strictly by confidence — NO shuffle. Engine rankings are the product.
  pool.sort((a: any, b: any) => {
    const aConf = a.enhanced_prob || a.cover_prob || 0.5
    const bConf = b.enhanced_prob || b.cover_prob || 0.5
    return bConf - aConf
  })

  // Take the top N picks by confidence — deterministic, engine-driven
  const selected = pool.slice(0, numLegs)
  
  console.log(`[ENGINE PICKS] ${numLegs}-leg parlay for ${email}:`, 
    selected.map((g: any) => `${g.pick} (${((g.enhanced_prob || g.cover_prob || 0.5) * 100).toFixed(1)}%)`).join(', '))

  // Build legs from ENGINE picks (spread or ML — always use what our model picked)
  const legs = selected.map((g: any) => {
    const isML = betType === 'moneyline'
    const pick = isML ? (g.ml_pick || g.pick) : g.pick
    const prob = isML ? (g.ml_prob || 0.5) : (g.enhanced_prob || g.cover_prob || 0.5)

    // Convert probability to American odds
    let odds: number
    if (prob >= 0.5) {
      odds = Math.round(-100 * prob / (1 - prob))
    } else {
      odds = Math.round(100 * (1 - prob) / prob)
    }

    return {
      gameId: `${g.home}_${g.away}`,
      team: pick || g.home,
      bet: isML
        ? `${pick} ML`
        : `${pick} ${g.spread_str || 'ATS'}`,
      odds,
      line: isML ? null : (g.spread || 0),
      type: isML ? 'moneyline' : 'spread',
      sport: g.sport || 'nba',
      homeTeam: g.home || '',
      awayTeam: g.away || '',
      confidence: Math.round(prob * 100),
      commence_time: g.commence_time,
      game_time: g.game_time,
    }
  })

  // Combined odds (multiply decimal odds)
  let decimalOdds = 1
  for (const leg of legs) {
    const dec = leg.odds > 0 ? (leg.odds / 100) + 1 : (100 / Math.abs(leg.odds)) + 1
    decimalOdds *= dec
  }
  const combinedAmerican = decimalOdds >= 2
    ? Math.round((decimalOdds - 1) * 100)
    : Math.round(-100 / (decimalOdds - 1))

  const avgConf = legs.reduce((s: number, l: any) => s + l.confidence, 0) / legs.length

  const pickIds = legs.map((l: any) => `${l.homeTeam}_${l.awayTeam}_${dateStr}`)

  return {
    id: Date.now(),
    legs,
    combinedOdds: (combinedAmerican >= 0 ? '+' : '') + combinedAmerican,
    confidence: Math.round(avgConf),
    expectedValue: 0,
    teams: legs.map((l: any) => l.team),
    payout: {
      bet10: Math.round(10 * decimalOdds * 100) / 100,
      bet25: Math.round(25 * decimalOdds * 100) / 100,
      bet50: Math.round(50 * decimalOdds * 100) / 100,
      bet100: Math.round(100 * decimalOdds * 100) / 100,
    },
    _pickIds: pickIds,
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { tier, sports, email: bodyEmail, sportsbook } = body

    const config = getTierConfig(tier)
    if (!config) {
      return NextResponse.json({ error: 'Invalid tier' }, { status: 400 })
    }

    // Get authenticated email (prefer session, fall back to body)
    let email = bodyEmail
    const cookie = req.cookies.get('parlayguarantee-session')
    if (cookie) {
      try {
        const decoded = jwt.verify(cookie.value, JWT_SECRET) as any
        if (decoded.email) email = decoded.email
      } catch {}
    }

    if (!email || !email.includes('@')) {
      return NextResponse.json({ error: 'Valid email required' }, { status: 400 })
    }

    // Validate sports selection
    const validSports = ['NBA', 'NCAAB', 'Mixed (NBA + NCAAB)']
    const sportsList: string[] = Array.isArray(sports) ? sports : sports ? [sports] : []
    if (sportsList.length === 0 || !sportsList.every((s: string) => validSports.includes(s))) {
      return NextResponse.json({ error: 'Select at least one valid sport' }, { status: 400 })
    }

    // Check daily purchase limits
    const limitCheck = await canUserPurchase(email, tier)
    if (!limitCheck.allowed) {
      return NextResponse.json({
        error: limitCheck.reason,
        currentCount: limitCheck.currentCount,
        limit: limitCheck.limit,
      }, { status: 429 })
    }

    const today = new Date().toISOString().split('T')[0]
    const excludePickIds = await getUserDailyPickIds(email)
    
    // Get current purchase count for unique seed per purchase
    const { getUserDailyPurchases } = await import('../../../lib/purchase-tracker')
    const dailyCounts = await getUserDailyPurchases(email)
    const purchaseCount = Object.values(dailyCounts).reduce((a, b) => a + b, 0)

    // Fetch OUR engine's analyzed games (not random Odds API)
    const analyzedGames = await fetchAnalyzedGames(today)

    const rawSport = sportsList[0]
    const sportKey = rawSport === 'Mixed (NBA + NCAAB)' ? undefined : rawSport?.toLowerCase().replace('ufc / mma', 'ufc').replace(/ /g, '')
    const isMLTier = tier.startsWith('ml-')
    const betType = isMLTier ? 'moneyline' as const : 'spread' as const

    let parlay = buildParlayFromEngine(
      analyzedGames, config.legs, email, today, purchaseCount, sportKey, betType, excludePickIds
    )

    // Fallback: try without sport filter
    if (!parlay && sportKey) {
      parlay = buildParlayFromEngine(
        analyzedGames, config.legs, email, today, purchaseCount, undefined, betType, excludePickIds
      )
    }

    if (!parlay) {
      return NextResponse.json({
        error: `Not enough games available to build ${config.legs === 1 ? 'a single pick' : `a ${config.legs}-leg parlay`}. Try a smaller tier or check back later.`,
      }, { status: 400 })
    }

    const pickIds = parlay._pickIds || []

    const stripe = getStripe()

    const paymentIntent = await stripe.paymentIntents.create({
      amount: config.priceInCents,
      currency: 'usd',
      capture_method: 'manual',
      metadata: {
        type: 'parlayguarantee_parlay',
        tier: tier,
        legs: config.legs.toString(),
        sports: sportsList.join(','),
        email,
        label: config.name,
        pick_ids: pickIds.join(','),
        parlay_data: JSON.stringify({
          legs: parlay.legs.map((l: any) => ({
            team: l.team,
            bet: l.bet,
            odds: l.odds,
            sport: l.sport,
          })),
          combinedOdds: parlay.combinedOdds,
          confidence: parlay.confidence,
        }).slice(0, 500),
        sportsbook: sportsbook || 'unknown',
        purchase_date: today,
      },
      ...(email ? { receipt_email: email } : {}),
    })

    return NextResponse.json({
      clientSecret: paymentIntent.client_secret,
      paymentIntentId: paymentIntent.id,
      tier: tier,
      amount: config.priceInCents,
      parlay: {
        legs: parlay.legs,
        combinedOdds: parlay.combinedOdds,
        confidence: parlay.confidence,
        payout: parlay.payout,
        teams: parlay.teams,
      },
    })
  } catch (error) {
    console.error('Checkout error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Checkout failed' },
      { status: 500 }
    )
  }
}
