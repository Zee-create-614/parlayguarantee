import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db_turso'

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { user_id, sport_category, bet_type, leg_count, payment_intent } = body

    if (!user_id || !sport_category || !bet_type || !leg_count) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
    }

    const today = new Date().toISOString().split('T')[0]

    // Find an available parlay not already dealt to this user
    const result = await db.execute({
      sql: `
        SELECT pp.* FROM parlay_pool pp
        LEFT JOIN dealt_tickets dt ON dt.pool_id = pp.id AND dt.user_id = ?
        WHERE pp.date = ?
          AND pp.sport_category = ?
          AND pp.bet_type = ?
          AND pp.leg_count = ?
          AND pp.is_active = 1
          AND dt.id IS NULL
        ORDER BY RANDOM()
        LIMIT 1
      `,
      args: [user_id, today, sport_category, bet_type, leg_count],
    })

    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'No available parlays for this tier' }, { status: 404 })
    }

    const parlay = result.rows[0]

    // Record the deal
    await db.execute({
      sql: `INSERT INTO dealt_tickets (user_id, pool_id, dealt_at, payment_intent) VALUES (?, ?, ?, ?)`,
      args: [user_id, parlay.id, new Date().toISOString(), payment_intent || null],
    })

    return NextResponse.json({
      ticket_id: parlay.id,
      sport_category: parlay.sport_category,
      bet_type: parlay.bet_type,
      leg_count: parlay.leg_count,
      combined_prob: parlay.combined_prob,
      implied_payout_per_100: parlay.implied_payout_per_100,
      picks: JSON.parse(parlay.picks_json as string),
    })
  } catch (err: any) {
    console.error('deal-ticket error:', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
