import { NextRequest, NextResponse } from 'next/server'
import jwt from 'jsonwebtoken'
import Stripe from 'stripe'
import { TIER_CONFIGS } from '../../../lib/tier-config'
import { getDFSLineupsForPurchases } from '../../../lib/dfs-tier-mapping'
import { getUser, getReferralCount, getBettingConfig, getFreePick, saveFreePick } from '../../../lib/kv'
import { generateUniqueParlay } from '../../../lib/parlay-engine'
import { Redis } from '@upstash/redis'
import { promises as fs } from 'fs'
import path from 'path'

const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-here'

function getStripe() {
  return new Stripe((process.env.STRIPE_SECRET_KEY || '').trim(), {
    apiVersion: '2026-01-28.clover',
  })
}

export async function GET(request: NextRequest) {
  try {
    const cookie = request.cookies.get('parlayguarantee-session')
    if (!cookie) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })
    }
    const decoded = jwt.verify(cookie.value, JWT_SECRET) as any
    if (decoded.type !== 'session') {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })
    }

    const email = decoded.email

    // Get user from KV
    let referralCode = ''
    let referralCountVal = 0
    let referralCredits = 0
    let bettingConfig = null

    try {
      const kvUser = await getUser(email)
      if (kvUser) {
        referralCode = kvUser.referralCode || ''
        referralCredits = kvUser.referralCredits || 0
        if (referralCode) {
          referralCountVal = await getReferralCount(referralCode)
        }
      }
    } catch (e) {
      console.error('KV error (user):', e)
    }

    // Fallback referral code from email hash
    if (!referralCode && email) {
      const crypto = require('crypto')
      referralCode = crypto.createHash('md5').update(email.toLowerCase()).digest('hex').slice(0, 8).toUpperCase()
    }

    // Get betting config from KV
    try {
      bettingConfig = await getBettingConfig(email)
    } catch (e) {
      console.error('KV error (betting):', e)
    }

    // Fetch purchases from Stripe
    const purchases: any[] = []
    let freeSignupPick: any = null
    let totalSpent = 0
    let totalRefunds = 0
    let wins = 0, losses = 0, pending = 0

    try {
      const stripe = getStripe()
      const paymentIntents = await stripe.paymentIntents.search({
        query: `metadata["email"]:"${email}" AND metadata["type"]:"parlayguarantee_parlay"`,
        limit: 50,
      })

      for (const pi of paymentIntents.data) {
        const tierConfig = TIER_CONFIGS[pi.metadata.tier]
        let legs: any[] = []
        let combinedOdds = ''
        let confidence = 0

        try {
          const parlayData = JSON.parse(pi.metadata.parlay_data || '{}')
          legs = parlayData.legs || []
          combinedOdds = parlayData.combinedOdds || ''
          confidence = parlayData.confidence || 0
        } catch {}

        let status = 'pending'
        // Handle both auto-capture (succeeded) and manual capture (requires_capture)
        if (pi.status === 'succeeded' || pi.status === 'requires_capture') {
          totalSpent += (pi.amount || 0) / 100
        }

        if (pi.status === 'canceled') {
          // Manual capture expired or was voided = refund (no charge)
          status = 'refunded'
          totalRefunds += (pi.amount || 0) / 100
          losses++
        } else if (pi.latest_charge) {
          try {
            const charge = await stripe.charges.retrieve(pi.latest_charge as string)
            if (charge.refunded) {
              status = 'refunded'
              totalRefunds += (charge.amount_refunded || 0) / 100
              losses++
            }
          } catch {}
        }

        if (status === 'pending' && (pi.status === 'succeeded' || pi.status === 'requires_capture')) {
          pending++
        }

        const pick = {
          id: pi.id,
          tier: pi.metadata.tier,
          tierName: tierConfig?.name || pi.metadata.tier,
          type: pi.metadata.purchase_type || 'purchase',
          sport: pi.metadata.sports || '',
          price: (pi.amount || 0) / 100,
          date: new Date((pi.created || 0) * 1000).toLocaleDateString('en-US'),
          status,
          legs,
          combinedOdds,
          confidence,
        }

        if (pi.metadata.purchase_type === 'free_signup') {
          freeSignupPick = pick
        }

        purchases.push(pick)
      }
    } catch (e) {
      console.error('Stripe error:', e)
    }

    // Check KV for free pick (and detect stale picks from previous days)
    if (!freeSignupPick) {
      try {
        const kvPick = await getFreePick(email)
        if (kvPick) {
          // Check if pick is stale (created on a previous day)
          const pickDate = kvPick.createdAt ? new Date(kvPick.createdAt).toISOString().split('T')[0] : null
          const today = new Date().toISOString().split('T')[0]
          const isStale = pickDate && pickDate < today

          if (isStale && kvPick.status === 'pending') {
            // Stale pending pick — regenerate with today's games
            console.log(`Free pick for ${email} is stale (${pickDate}), regenerating...`)
            try {
              const freshParlay = await generateUniqueParlay(3)
              if (freshParlay) {
                const freshData = {
                  parlayData: freshParlay.legs.map((l: any) => ({
                    home: l.homeTeam || '',
                    away: l.awayTeam || '',
                    pick: l.team,
                    win_prob: l.confidence ? l.confidence / 100 : 0.5,
                  })),
                  legs: freshParlay.legs,
                  combinedOdds: freshParlay.combinedOdds,
                  confidence: freshParlay.confidence,
                  sport: freshParlay.sport || 'NBA',
                  status: 'pending',
                }
                await saveFreePick(email, freshData)
                // Build display from fresh data instead of stale kvPick
                freeSignupPick = {
                  id: 'free_signup',
                  tier: '3leg',
                  tierName: '3-Leg Parlay (Free)',
                  type: 'free_signup',
                  sport: freshParlay.sport || 'NBA',
                  price: 0,
                  date: new Date().toLocaleDateString('en-US'),
                  status: 'pending',
                  legs: freshParlay.legs.map((l: any) => ({
                    team: `${l.awayTeam} @ ${l.homeTeam}`,
                    bet: l.bet,
                    odds: l.odds,
                    type: l.type,
                    sport: l.sport,
                    result: undefined,
                  })),
                  combinedOdds: freshParlay.combinedOdds,
                  confidence: freshParlay.confidence,
                }
              }
            } catch (regenErr) {
              console.warn('Free pick regeneration failed, showing stale:', regenErr)
            }
          }

          if (!freeSignupPick && kvPick) {
          // Handle both old format ({away, home, pick, win_prob}) and new format ({away_team, home_team, bet, odds, team})
          const legs = (kvPick.parlayData || kvPick.legs || []).map((g: any) => {
            // New format from live parlay engine
            if (g.odds !== undefined && g.bet) {
              return {
                team: g.team || `${g.away_team || g.awayTeam || ''} @ ${g.home_team || g.homeTeam || ''}`,
                bet: g.bet,
                odds: g.odds,
                type: g.bet_type || g.type || 'spread',
                sport: g.sport || 'nba',
                result: undefined,
              }
            }
            // Old format from picks_output.json
            const winProb = g.win_prob || 0.5
            let americanOdds: number
            if (winProb >= 0.5) {
              americanOdds = Math.round(-100 * winProb / (1 - winProb))
            } else {
              americanOdds = Math.round(100 * (1 - winProb) / winProb)
            }
            return {
              team: `${g.away || g.away_team || ''} @ ${g.home || g.home_team || ''}`,
              bet: `${g.pick || g.predicted_winner || ''} ML`,
              odds: americanOdds,
              type: 'moneyline',
              sport: g.sport || 'NBA',
              result: undefined,
            }
          })
          freeSignupPick = {
            id: 'free_signup',
            tier: '3leg',
            tierName: '3-Leg Parlay (Free)',
            type: 'free_signup',
            sport: kvPick.sport || 'NBA',
            price: 0,
            date: kvPick.createdAt || '',
            status: kvPick.status || 'pending',
            legs,
            combinedOdds: kvPick.combinedOdds || '',
            confidence: kvPick.confidence || 0,
          }
          }
        }
      } catch {}
    }

    // Generate free pick on first visit if user has no purchases and no free pick yet
    if (!freeSignupPick && purchases.length === 0) {
      try {
        const generatedParlay = await generateUniqueParlay(3) // 3-leg free parlay
        if (generatedParlay) {
          // Save to KV for persistence
          const pickData = {
            parlayData: generatedParlay.legs.map(l => ({
              home: l.homeTeam || '',
              away: l.awayTeam || '',
              pick: l.team,
              win_prob: l.confidence ? l.confidence / 100 : 0.5,
            })),
            legs: generatedParlay.legs,
            combinedOdds: generatedParlay.combinedOdds,
            confidence: generatedParlay.confidence,
            sport: generatedParlay.sport || 'NBA',
            status: 'pending',
          }
          await saveFreePick(email, pickData)

          freeSignupPick = {
            id: 'free_signup',
            tier: '3leg',
            tierName: '3-Leg Parlay (Free)',
            type: 'free_signup',
            sport: generatedParlay.sport || 'NBA',
            price: 0,
            date: new Date().toLocaleDateString('en-US'),
            status: 'pending',
            legs: generatedParlay.legs.map(l => ({
              team: `${l.awayTeam} @ ${l.homeTeam}`,
              bet: l.bet,
              odds: l.odds,
              type: l.type,
              sport: l.sport,
              result: undefined,
            })),
            combinedOdds: generatedParlay.combinedOdds,
            confidence: generatedParlay.confidence,
          }
        }
      } catch (e) {
        console.error('Free pick generation error:', e)
      }
    }

    // Final fallback: picks_output.json
    if (!freeSignupPick && !decoded.freePackUsed) {
      try {
        const picksFile = path.join(process.cwd(), 'engine', 'picks_output.json')
        const picksRaw = await fs.readFile(picksFile, 'utf-8')
        const picksData = JSON.parse(picksRaw)
        const tier3 = picksData['3leg']
        const parlay = tier3?.picks?.[0]
        if (parlay) {
          const legs = (parlay.games || []).map((g: any) => {
            const winProb = g.win_prob || 0.5
            let americanOdds: number
            if (winProb >= 0.5) {
              americanOdds = Math.round(-100 * winProb / (1 - winProb))
            } else {
              americanOdds = Math.round(100 * (1 - winProb) / winProb)
            }
            return {
              team: `${g.away} @ ${g.home}`,
              bet: `${g.pick} ML`,
              odds: americanOdds,
              type: 'moneyline',
              sport: 'NBA',
              result: undefined,
            }
          })
          freeSignupPick = {
            id: 'free_signup',
            tier: '3leg',
            tierName: '3-Leg Parlay (Free)',
            type: 'free_signup',
            sport: 'NBA',
            price: 0,
            date: picksData.generated_at || new Date().toISOString(),
            status: 'pending',
            legs,
            combinedOdds: parlay.implied_payout || '',
            confidence: parlay.combined_prob || 0,
          }
        }
      } catch (e) {
        console.error('Free pick fallback failed:', e)
      }
    }

    // Match purchases against actual results from KV
    try {
      const kvUrl = (process.env.UPSTASH_REDIS_REST_URL || '').trim()
      const kvToken = (process.env.UPSTASH_REDIS_REST_TOKEN || '').trim()
      if (kvUrl && kvToken) {
        const kvRedis = new Redis({ url: kvUrl, token: kvToken })
        const exportData = await kvRedis.get<{ pick_results: any[]; daily_summaries: any[] }>('results:export')
        if (exportData?.pick_results) {
          // Build a lookup: date → { predicted_winner → correct (0/1/null) }
          const resultLookup: Record<string, Record<string, number | null>> = {}
          for (const pr of exportData.pick_results) {
            const d = pr.date
            if (!resultLookup[d]) resultLookup[d] = {}
            resultLookup[d][pr.predicted_winner] = pr.correct
          }

          // Update purchase statuses based on results
          wins = 0; losses = 0; pending = 0
          for (const purchase of purchases) {
            if (purchase.status === 'refunded') continue
            const purchaseDate = new Date(purchase.date)
            const dateKey = purchaseDate.toISOString().split('T')[0]
            
            // Check if any leg results exist for this purchase date
            const dayResults = resultLookup[dateKey]
            if (!dayResults) { pending++; continue }

            // Check legs
            let allResolved = true
            let allCorrect = true
            for (const leg of purchase.legs) {
              const team = leg.team?.split(' @ ') || []
              const pick = leg.bet?.replace(' ML', '') || ''
              if (dayResults[pick] === 1) {
                leg.result = 'won'
              } else if (dayResults[pick] === 0) {
                leg.result = 'lost'
                allCorrect = false
              } else {
                allResolved = false
              }
            }

            if (allResolved && purchase.legs.length > 0) {
              purchase.status = allCorrect ? 'won' : 'lost'
              if (allCorrect) wins++; else losses++
            } else {
              pending++
            }
          }
        }
      }
    } catch (e) {
      console.error('KV result matching error:', e)
    }

    // DFS lineups
    let dfsLineups: any[] = []
    try {
      const dfsFile = path.join(process.cwd(), 'engine', 'dfs_output.json')
      const dfsRaw = await fs.readFile(dfsFile, 'utf-8')
      const dfsData = JSON.parse(dfsRaw)
      dfsLineups = getDFSLineupsForPurchases(dfsData, purchases, true)
    } catch (e) {
      console.error('DFS lineups error:', e)
    }

    return NextResponse.json({
      email,
      referral: {
        code: referralCode,
        count: referralCountVal,
        credits: referralCredits,
      },
      bettingConfig,
      purchases,
      pickResults: { wins, losses, pushes: 0, pending },
      roi: { totalSpent, totalRefunds, netCost: totalSpent - totalRefunds },
      freeSignupPick,
      dfsLineups,
    })
  } catch (error: any) {
    console.error('Dashboard API error:', error)
    return NextResponse.json({ error: 'Server error' }, { status: 500 })
  }
}
