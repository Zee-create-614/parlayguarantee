import { NextRequest, NextResponse } from 'next/server'

const API_KEY = (process.env.ODDS_API_KEY || 'f3c9f91dc369f56dea1b523d3071e1f1').trim()
const BASE_URL = 'https://api.the-odds-api.com/v4'

const SPORT_KEYS = [
  'basketball_nba',
  'basketball_ncaab',
] as const

const SPORT_MAP: Record<string, string> = {
  basketball_nba: 'nba',
  icehockey_nhl: 'nhl',
  baseball_mlb: 'mlb',
  mma_mixed_martial_arts: 'ufc',
  soccer_epl: 'soccer',
  basketball_ncaab: 'ncaab',
}

// In-memory cache
let cache: { data: any; timestamp: number } | null = null
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

interface OddsAPIEvent {
  id: string
  sport_key: string
  sport_title: string
  commence_time: string
  home_team: string
  away_team: string
  bookmakers: {
    key: string
    title: string
    markets: {
      key: string // h2h, spreads, totals
      outcomes: {
        name: string
        price: number
        point?: number
      }[]
    }[]
  }[]
}

function extractBestOdds(bookmakers: OddsAPIEvent['bookmakers']) {
  // Use first available bookmaker (usually FanDuel/DraftKings)
  const book = bookmakers[0]
  if (!book) return null

  const markets: Record<string, any> = {}
  for (const market of book.markets) {
    markets[market.key] = market.outcomes
  }

  return markets
}

async function fetchAllOdds(): Promise<any[]> {
  // Check cache
  if (cache && Date.now() - cache.timestamp < CACHE_TTL) {
    return cache.data
  }

  const allEvents: any[] = []

  // Fetch all sports in parallel with a single markets param to minimize calls
  const results = await Promise.allSettled(
    SPORT_KEYS.map(async (sportKey) => {
      const url = `${BASE_URL}/sports/${sportKey}/odds/?apiKey=${API_KEY}&regions=us&markets=h2h,spreads,totals&oddsFormat=american`
      const res = await fetch(url, { cache: 'no-store' })
      if (!res.ok) {
        console.error(`Odds API error for ${sportKey}: ${res.status}`)
        return []
      }
      const events: OddsAPIEvent[] = await res.json()
      return events.map((event) => {
        const odds = extractBestOdds(event.bookmakers)
        const h2h = odds?.h2h || []
        const spreads = odds?.spreads || []
        const totals = odds?.totals || []

        const homeH2h = h2h.find((o: any) => o.name === event.home_team)
        const awayH2h = h2h.find((o: any) => o.name === event.away_team)
        const homeSpread = spreads.find((o: any) => o.name === event.home_team)
        const awaySpread = spreads.find((o: any) => o.name === event.away_team)
        const over = totals.find((o: any) => o.name === 'Over')
        const under = totals.find((o: any) => o.name === 'Under')

        return {
          id: event.id,
          sport: SPORT_MAP[event.sport_key] || event.sport_key,
          sportKey: event.sport_key,
          homeTeam: event.home_team,
          awayTeam: event.away_team,
          startTime: event.commence_time,
          status: 'scheduled' as const,
          moneyline: {
            home: homeH2h?.price ?? 0,
            away: awayH2h?.price ?? 0,
          },
          spread: {
            home: homeSpread?.point ?? 0,
            away: awaySpread?.point ?? 0,
            homeOdds: homeSpread?.price ?? -110,
            awayOdds: awaySpread?.price ?? -110,
          },
          total: {
            over: over?.point ?? 0,
            under: under?.point ?? 0,
            overOdds: over?.price ?? -110,
            underOdds: under?.price ?? -110,
          },
          bookmaker: event.bookmakers[0]?.title || 'N/A',
        }
      })
    })
  )

  for (const result of results) {
    if (result.status === 'fulfilled') {
      allEvents.push(...result.value)
    }
  }

  // Update cache
  cache = { data: allEvents, timestamp: Date.now() }
  return allEvents
}

export async function GET(request: NextRequest) {
  try {
    const sport = request.nextUrl.searchParams.get('sport')
    let events = await fetchAllOdds()

    if (sport) {
      events = events.filter((e: any) => e.sport === sport)
    }

    return NextResponse.json({
      events,
      count: events.length,
      cachedAt: cache?.timestamp ? new Date(cache.timestamp).toISOString() : null,
      sports: [...new Set(events.map((e: any) => e.sport))],
    })
  } catch (error) {
    console.error('Odds API error:', error)
    return NextResponse.json({ error: 'Failed to fetch odds', events: [] }, { status: 500 })
  }
}
