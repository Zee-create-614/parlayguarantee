import { NextRequest, NextResponse } from 'next/server'
import Stripe from 'stripe'
import jwt from 'jsonwebtoken'
import { promises as fs } from 'fs'
import path from 'path'
import { getTierConfig } from '../../../lib/tier-config'
import { canUserPurchase, getUserDailyPickIds } from '../../../lib/purchase-tracker'
import { recordPurchaseInstant, getInstantPickIds } from '../../../lib/kv'
import { getClient } from '../../../../engine/db'
import { generateUserParlays, gameConf } from '../../../lib/parlay-engine'

const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-here'
const ANALYZED_GAMES_FILE = path.join(process.cwd(), 'engine', 'analyzed_games.json')

function getStripe() {
  return new Stripe((process.env.STRIPE_SECRET_KEY || '').trim(), {
    apiVersion: '2026-01-28.clover',
  })
}

// ─── Fetch analyzed games (Turso primary, local JSON fallback) ───
async function fetchAnalyzedGames(pickDate: string): Promise<any[]> {
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
          book_count: row.book_count, bookmakers: row.bookmakers || '', game_date: row.pick_date,
        }
      })
    }
  } catch (e) {
    console.error('Turso fetch failed:', e)
  }
  try {
    const raw = await fs.readFile(ANALYZED_GAMES_FILE, 'utf-8')
    return JSON.parse(raw)
  } catch {
    return []
  }
}

// ─── Map checkout tier → picks product ID ───
// This ensures checkout generates picks using the EXACT same algorithm as /api/picks
function tierToProductId(tier: string): string {
  if (tier.startsWith('ml-')) return 'parlay-ml-safe'
  // Default spread tiers use 'parlay-consistent' — the highest-confidence product
  return 'parlay-consistent'
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
    const stripePickIds = await getUserDailyPickIds(email)
    const instantPickIds = await getInstantPickIds(email)
    const excludePickIds = [...new Set([...stripePickIds, ...instantPickIds])]

    // Count existing purchases to generate a unique parlay set per purchase
    const { getInstantPurchases } = await import('../../../lib/kv')
    const existingPurchases = await getInstantPurchases(email)
    const purchaseIndex = existingPurchases.length

    // Fetch engine's analyzed games (same Turso-first source as /api/picks)
    const analyzedGames = await fetchAnalyzedGames(today)

    // ─── Use the SAME generateUserParlays function as /api/picks ───
    // This guarantees the user gets exactly the picks they were shown on the site.
    const productId = tierToProductId(tier)
    const allParlays = generateUserParlays(analyzedGames, email, productId, today, sportsbook || undefined, purchaseIndex)

    // Build set of previously purchased parlay signatures to prevent exact duplicates
    const prevParlaySignatures = new Set<string>()
    for (const purchase of existingPurchases) {
      if (purchase.parlayData?.legs) {
        const sig = purchase.parlayData.legs
          .map((l: any) => `${l.team}|${l.bet}`)
          .sort()
          .join('::')
        prevParlaySignatures.add(sig)
      }
    }

    // Find a parlay matching the requested leg count that doesn't overlap with prior purchases
    const targetLegs = config.legs
    let selectedParlay: any = null

    for (const p of allParlays) {
      if (p.legs !== targetLegs) continue

      // Check for exact duplicate with previously purchased parlays
      const parlayGames = p.games || []
      const isML = tier.startsWith('ml-') || p.pick_mode === 'moneyline'
      const sig = parlayGames
        .map((g: any) => {
          const pick = isML ? (g.ml_pick || g.pick) : g.pick
          const bet = isML ? `${pick} ML` : `${pick} ${g.spread_str || 'ATS'}`
          return `${pick}|${bet}`
        })
        .sort()
        .join('::')
      if (prevParlaySignatures.has(sig)) continue

      // Check for overlap with already-purchased picks
      const parlayPickIds = parlayGames.map((g: any) =>
        `${g.home || g.home_team}_${g.away || g.away_team}_${g.game_date || today}`
      )
      const hasOverlap = parlayPickIds.some((id: string) => excludePickIds.includes(id))
      if (hasOverlap) continue

      selectedParlay = p
      break
    }

    // Fallback: skip overlap check but still enforce no exact duplicates
    if (!selectedParlay) {
      for (const p of allParlays) {
        if (p.legs !== targetLegs) continue
        const parlayGames = p.games || []
        const isML = tier.startsWith('ml-') || p.pick_mode === 'moneyline'
        const sig = parlayGames
          .map((g: any) => {
            const pick = isML ? (g.ml_pick || g.pick) : g.pick
            const bet = isML ? `${pick} ML` : `${pick} ${g.spread_str || 'ATS'}`
            return `${pick}|${bet}`
          })
          .sort()
          .join('::')
        if (!prevParlaySignatures.has(sig)) {
          selectedParlay = p
          break
        }
      }
    }

    // Last resort: try with incremented purchaseIndex to generate fresh combos
    if (!selectedParlay) {
      for (let extra = 1; extra <= 5; extra++) {
        const freshParlays = generateUserParlays(analyzedGames, email, productId, today, sportsbook || undefined, purchaseIndex + extra)
        for (const p of freshParlays) {
          if (p.legs !== targetLegs) continue
          const parlayGames = p.games || []
          const isML = tier.startsWith('ml-') || p.pick_mode === 'moneyline'
          const sig = parlayGames
            .map((g: any) => {
              const pick = isML ? (g.ml_pick || g.pick) : g.pick
              const bet = isML ? `${pick} ML` : `${pick} ${g.spread_str || 'ATS'}`
              return `${pick}|${bet}`
            })
            .sort()
            .join('::')
          if (!prevParlaySignatures.has(sig)) {
            selectedParlay = p
            break
          }
        }
        if (selectedParlay) break
      }
    }

    if (!selectedParlay) {
      return NextResponse.json({
        error: `Not enough games available to build ${targetLegs === 1 ? 'a single pick' : `a ${targetLegs}-leg parlay`}. Try a smaller tier or check back later.`,
      }, { status: 400 })
    }

    // ─── Build response legs from engine parlay (same format as before) ───
    const isML = tier.startsWith('ml-') || selectedParlay.pick_mode === 'moneyline'
    const legs = (selectedParlay.games || []).map((g: any) => {
      const pick = isML ? (g.ml_pick || g.pick) : g.pick
      const prob = isML ? (g.ml_prob || 0.5) : gameConf(g)

      let odds: number
      if (prob >= 0.5) {
        odds = Math.round(-100 * prob / (1 - prob))
      } else {
        odds = Math.round(100 * (1 - prob) / prob)
      }

      return {
        gameId: `${g.home || g.home_team}_${g.away || g.away_team}`,
        team: pick || g.home || g.home_team || '',
        bet: isML
          ? `${pick} ML`
          : `${pick} ${g.spread_str || 'ATS'}`,
        odds,
        line: isML ? null : (g.spread || 0),
        type: isML ? 'moneyline' : 'spread',
        sport: g.sport || 'nba',
        homeTeam: g.home || g.home_team || '',
        awayTeam: g.away || g.away_team || '',
        confidence: Math.round(prob * 100),
        commence_time: g.commence_time,
        game_time: g.game_time,
      }
    })

    // Combined odds
    let decimalOdds = 1
    for (const leg of legs) {
      const dec = leg.odds > 0 ? (leg.odds / 100) + 1 : (100 / Math.abs(leg.odds)) + 1
      decimalOdds *= dec
    }
    const combinedAmerican = decimalOdds >= 2
      ? Math.round((decimalOdds - 1) * 100)
      : Math.round(-100 / (decimalOdds - 1))

    const avgConf = legs.reduce((s: number, l: any) => s + l.confidence, 0) / legs.length

    const pickIds = legs.map((l: any) => `${l.homeTeam}_${l.awayTeam}_${today}`)

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
          legs: legs.map((l: any) => ({
            team: l.team,
            bet: l.bet,
            odds: l.odds,
            sport: l.sport,
          })),
          combinedOdds: (combinedAmerican >= 0 ? '+' : '') + combinedAmerican,
          confidence: Math.round(avgConf),
        }).slice(0, 500),
        sportsbook: sportsbook || 'unknown',
        purchase_date: today,
      },
      ...(email ? { receipt_email: email } : {}),
    })

    try {
      await recordPurchaseInstant(email, paymentIntent.id, tier, pickIds, {
        legs: legs.map((l: any) => ({ team: l.team, bet: l.bet, odds: l.odds, sport: l.sport, homeTeam: l.homeTeam, awayTeam: l.awayTeam, confidence: l.confidence, commence_time: l.commence_time, game_time: l.game_time, line: l.line, type: l.type })),
        combinedOdds: (combinedAmerican >= 0 ? '+' : '') + combinedAmerican,
        confidence: Math.round(avgConf),
      })
    } catch (e) { console.error('Failed to record instant purchase:', e) }

    return NextResponse.json({
      clientSecret: paymentIntent.client_secret,
      paymentIntentId: paymentIntent.id,
      tier: tier,
      amount: config.priceInCents,
      parlay: {
        legs,
        combinedOdds: (combinedAmerican >= 0 ? '+' : '') + combinedAmerican,
        confidence: Math.round(avgConf),
        payout: {
          bet10: Math.round(10 * decimalOdds * 100) / 100,
          bet25: Math.round(25 * decimalOdds * 100) / 100,
          bet50: Math.round(50 * decimalOdds * 100) / 100,
          bet100: Math.round(100 * decimalOdds * 100) / 100,
        },
        teams: legs.map((l: any) => l.team),
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
