import { NextRequest, NextResponse } from 'next/server'
import { getClient } from '../../../../engine/db'

const PRODUCT_MAP: Record<string, string[]> = {
  all: ['nba_engine', 'ncaab_engine', 'nba_ou', 'ncaab_ou'],
  nba: ['nba_engine', 'nba_ou'],
  ncaab: ['ncaab_engine', 'ncaab_ou'],
}

export async function GET(request: NextRequest) {
  try {
    const product = request.nextUrl.searchParams.get('product') || 'all'
    const products = PRODUCT_MAP[product] || PRODUCT_MAP.all

    const client = getClient()
    const placeholders = products.map(() => '?').join(',')

    // Fetch pick results
    const resultsRes = await client.execute({
      sql: `SELECT * FROM pick_results WHERE product IN (${placeholders}) ORDER BY date DESC, pick_number ASC LIMIT 500`,
      args: products,
    })

    // Fetch daily summaries
    const summariesRes = await client.execute({
      sql: `SELECT * FROM daily_summaries WHERE product IN (${placeholders}) ORDER BY date DESC LIMIT 100`,
      args: products,
    })

    const results = resultsRes.rows as any[]
    const summaries = summariesRes.rows as any[]

    if (!summaries || summaries.length === 0) {
      return NextResponse.json({
        results: [],
        stats: null,
        daySummaries: [],
        isBacktest: true,
      })
    }

    // Aggregate stats
    let straightCorrect = 0, straightTotal = 0
    let spreadCorrect = 0, spreadTotal = 0
    let ouCorrect = 0, ouTotal = 0
    const dateSet = new Set<string>()

    for (const s of summaries) {
      dateSet.add(s.date)
      straightCorrect += Number(s.correct_picks || 0)
      straightTotal += Number(s.total_picks || 0)
      spreadCorrect += Number(s.spread_correct || 0)
      spreadTotal += Number(s.spread_total || 0)
      ouCorrect += Number(s.ou_correct || 0)
      ouTotal += Number(s.ou_total || 0)
    }

    // Group summaries by date for day-by-day view
    const byDate: Record<string, { straightCorrect: number; straightTotal: number; spreadCorrect: number; spreadTotal: number; ouCorrect: number; ouTotal: number }> = {}
    for (const s of summaries) {
      if (!byDate[s.date]) {
        byDate[s.date] = { straightCorrect: 0, straightTotal: 0, spreadCorrect: 0, spreadTotal: 0, ouCorrect: 0, ouTotal: 0 }
      }
      const d = byDate[s.date]
      d.straightCorrect += Number(s.correct_picks || 0)
      d.straightTotal += Number(s.total_picks || 0)
      d.spreadCorrect += Number(s.spread_correct || 0)
      d.spreadTotal += Number(s.spread_total || 0)
      d.ouCorrect += Number(s.ou_correct || 0)
      d.ouTotal += Number(s.ou_total || 0)
    }

    const daySummaries = Object.entries(byDate)
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([date, d]) => ({ date, ...d }))

    return NextResponse.json({
      results,
      stats: {
        straightAccuracy: straightTotal > 0 ? Math.round((straightCorrect / straightTotal) * 1000) / 10 : 0,
        straightCorrect,
        straightTotal,
        spreadAccuracy: spreadTotal > 0 ? Math.round((spreadCorrect / spreadTotal) * 1000) / 10 : 0,
        spreadCorrect,
        spreadTotal,
        ouAccuracy: ouTotal > 0 ? Math.round((ouCorrect / ouTotal) * 1000) / 10 : 0,
        ouCorrect,
        ouTotal,
        daysTracked: dateSet.size,
      },
      daySummaries,
      isBacktest: false,
    })
  } catch (error) {
    console.error('Error fetching results:', error)
    return NextResponse.json({ error: 'Failed to fetch results' }, { status: 500 })
  }
}
