import { NextRequest, NextResponse } from 'next/server'
import { getClient } from '../../../../../engine/db'

export async function POST(request: NextRequest) {
  try {
    const client = getClient()

    // Get all unscored tickets
    const ticketsResult = await client.execute(
      'SELECT * FROM tickets WHERE all_scored = 0'
    )
    const tickets = ticketsResult.rows
    if (!tickets || tickets.length === 0) {
      return NextResponse.json({ message: 'No unscored tickets', scored: 0 })
    }

    let scored = 0
    for (const ticket of tickets) {
      const legs = JSON.parse(ticket.legs_json as string) as any[]
      const pickDate = ticket.pick_date as string

      // Get daily_picks for this date
      const picksResult = await client.execute({
        sql: 'SELECT * FROM daily_picks WHERE pick_date = ?',
        args: [pickDate]
      })
      const picks = picksResult.rows
      if (!picks || picks.length === 0) continue // can't score yet

      let won = 0, lost = 0, pushed = 0, pending = 0

      for (const leg of legs) {
        // Match leg to a daily_pick by home+away
        const match = picks.find((p: any) =>
          p.home === leg.home && p.away === leg.away
        )
        if (!match || !match.raw_json) {
          pending++
          continue
        }

        // Check if result data exists in raw_json
        let raw: any
        try { raw = JSON.parse(match.raw_json as string) } catch { pending++; continue }

        // We need actual scores to grade — if no result yet, it's pending
        if (!raw.result) {
          pending++
          continue
        }

        const result = raw.result
        const legPick = leg.pick
        const legType = leg.type || 'spread'

        if (legType === 'spread') {
          const margin = result.home_score - result.away_score
          // Use the ticket's own stamped spread line, not the daily_picks table
          const spreadVal = leg.spread_at_purchase != null
            ? (typeof leg.spread_at_purchase === 'number' ? leg.spread_at_purchase : parseFloat(leg.spread_at_purchase))
            : (match.spread as number)
          const adjusted = legPick === leg.home_team
            ? margin + spreadVal
            : -margin - spreadVal
          if (adjusted > 0) won++
          else if (adjusted === 0) pushed++
          else lost++
        } else if (legType === 'total') {
          const total = result.home_score + result.away_score
          // Use the ticket's own stamped total line, not the daily_picks table
          const line = leg.spread_at_purchase != null
            ? (typeof leg.spread_at_purchase === 'number' ? leg.spread_at_purchase : parseFloat(leg.spread_at_purchase))
            : (match.total_line as number)
          if (leg.pick === 'Over' && total > line) won++
          else if (leg.pick === 'Under' && total < line) won++
          else if (total === line) pushed++
          else lost++
        } else {
          // ML
          if (legPick === result.winner) won++
          else lost++
        }
      }

      // Determine deposit_status
      const totalLegs = legs.length
      const allDone = pending === 0
      let depositStatus = 'held'

      if (allDone) {
        const effectiveLegs = totalLegs - pushed // pushes don't count
        if (effectiveLegs === 0) {
          depositStatus = 'released' // all pushes → we keep the deposit
        } else if (totalLegs === 1) {
          // Single pick: won → released (we keep deposit), lost → refund_eligible (user gets deposit back)
          depositStatus = won > 0 ? 'released' : 'refund_eligible'
        } else {
          // Parlay: ALL must win (excluding pushes)
          // won → released (we keep deposit, user got winning picks)
          // lost → refund_eligible (user gets deposit back per guarantee)
          depositStatus = lost === 0 ? 'released' : 'refund_eligible'
        }
      }

      await client.execute({
        sql: `UPDATE tickets SET
          legs_won = ?, legs_lost = ?, legs_pushed = ?, legs_pending = ?,
          all_scored = ?, deposit_status = ?, scored_at = CASE WHEN ? = 1 THEN datetime('now') ELSE scored_at END
          WHERE id = ?`,
        args: [
          won, lost, pushed, pending,
          allDone ? 1 : 0,
          depositStatus,
          allDone ? 1 : 0,
          ticket.id
        ]
      })
      scored++
    }

    return NextResponse.json({ message: `Scored ${scored} tickets`, scored })
  } catch (error) {
    console.error('Ticket scoring error:', error)
    return NextResponse.json({ error: 'Scoring failed' }, { status: 500 })
  }
}
