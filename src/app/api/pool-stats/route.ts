import { NextResponse } from 'next/server'
import { db } from '@/lib/db_turso'

export async function GET() {
  try {
    const today = new Date().toISOString().split('T')[0]

    // Get pool counts grouped by category
    const poolResult = await db.execute({
      sql: `
        SELECT sport_category, bet_type, leg_count, COUNT(*) as cnt
        FROM parlay_pool
        WHERE date = ? AND is_active = 1
        GROUP BY sport_category, bet_type, leg_count
        ORDER BY sport_category, bet_type, leg_count
      `,
      args: [today],
    })

    // Get dealt count
    const dealtResult = await db.execute({
      sql: `
        SELECT COUNT(*) as cnt FROM dealt_tickets dt
        JOIN parlay_pool pp ON pp.id = dt.pool_id
        WHERE pp.date = ?
      `,
      args: [today],
    })

    const categories: Record<string, Record<string, Record<string, number>>> = {}
    let total = 0

    for (const row of poolResult.rows) {
      const sc = row.sport_category as string
      const bt = row.bet_type as string
      const lc = row.leg_count as number
      const cnt = row.cnt as number
      total += cnt

      if (!categories[sc]) categories[sc] = {}
      if (!categories[sc][bt]) categories[sc][bt] = {}
      categories[sc][bt][`${lc}leg`] = cnt
    }

    return NextResponse.json({
      date: today,
      categories,
      total_parlays: total,
      dealt_today: Number(dealtResult.rows[0]?.cnt ?? 0),
    })
  } catch (err: any) {
    console.error('pool-stats error:', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
