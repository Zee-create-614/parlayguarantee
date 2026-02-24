import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'
// generateParlays/fetchGames removed — all picks must come from engine analysis only
import { getClient, initializeDatabase } from '../../../../engine/db'
import {
  generateUserParlays,
  gameConf,
  computeHomAwayProb,
  gameSport,
  isMixedSportCombo,
  PRODUCT_IDS,
} from '../../../lib/parlay-engine'

// Filter games to only those available on a specific sportsbook
function filterBySportsbook(games: any[], sportsbook: string): any[] {
  if (!sportsbook) return games
  return games.filter((g: any) => {
    const books: string[] = g.available_books || g.availableBooks || []
    return books.some((b: string) => b.toLowerCase() === sportsbook.toLowerCase())
  })
}

const PICKS_FILE = path.join(process.cwd(), 'engine', 'picks_output.json')
const ANALYZED_GAMES_FILE = path.join(process.cwd(), 'engine', 'analyzed_games.json')
const DFS_FILE = path.join(process.cwd(), 'engine', 'dfs_output.json')

// Fetch analyzed games from Turso cloud DB (primary source)
async function fetchGamesFromTurso(pickDate: string): Promise<any[] | null> {
  try {
    const client = getClient()
    const result = await client.execute({
      sql: 'SELECT * FROM daily_picks WHERE pick_date = ?',
      args: [pickDate]
    })
    if (!result.rows || result.rows.length === 0) return null

    return result.rows.map((row: any) => {
      // If raw_json exists, parse it for full game data
      if (row.raw_json) {
        try {
          return JSON.parse(row.raw_json)
        } catch {
          // fall through to manual mapping
        }
      }
      return {
        sport: row.sport,
        home: row.home,
        away: row.away,
        spread: row.spread,
        spread_str: row.spread_str,
        pick: row.pick,
        cover_prob: row.cover_prob,
        enhanced_prob: row.enhanced_prob,
        ml_pick: row.ml_pick,
        ml_prob: row.ml_prob,
        total_line: row.total_line,
        ou_pick: row.ou_pick,
        ou_prob: row.ou_prob,
        upset_score: row.upset_score,
        upset_flip: row.upset_flip === 1,
        game_time: row.game_time,
        commence_time: row.commence_time,
        book_count: row.book_count,
        game_date: row.pick_date,
      }
    })
  } catch (e) {
    console.error('Turso fetch failed, falling back to JSON:', e)
    return null
  }
}

// Per-user parlay generation now imported from shared lib: src/lib/parlay-engine.ts
// (generateUserParlays, gameConf, computeHomAwayProb, gameSport, isMixedSportCombo, PRODUCT_IDS)

interface EngineGame {
  home_team: string
  away_team: string
  game_date: string
  game_time: string
  predicted_winner: string
  confidence: number
  home_probability: number
  away_probability: number
  factors?: Record<string, number>
  model_score?: number
  closing_line_value?: number
  error?: string
}

interface EnginePick {
  pick_number: number
  type: 'parlay' | 'straight'
  legs?: number
  games: EngineGame[]
  combined_confidence?: number
  implied_payout?: string
  confidence?: number
  predicted_winner?: string
}

interface EngineProduct {
  product_name: string
  date: string
  generated_at: string
  picks: EnginePick[]
  total_picks: number
}

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const product = searchParams.get('product')
    const preview = searchParams.get('preview') === 'true'
    // live parameter removed — all picks come from engine only
    const userId = searchParams.get('user_id')?.trim() || ''
    const sportsbook = searchParams.get('sportsbook')?.trim() || ''

    // --- Per-user unique parlays: if user_id provided and analyzed_games exist ---
    if (userId) {
      try {
        const today = new Date().toISOString().split('T')[0]
        // PRIMARY: Turso cloud DB. FALLBACK: local JSON file.
        let analyzedGames = await fetchGamesFromTurso(today)
        if (!analyzedGames) {
          const raw = await fs.readFile(ANALYZED_GAMES_FILE, 'utf-8')
          analyzedGames = JSON.parse(raw)
        }
        // (analyzedGames is already defined)
        if (sportsbook && Array.isArray(analyzedGames)) {
          analyzedGames = filterBySportsbook(analyzedGames, sportsbook)
        }
        if (Array.isArray(analyzedGames) && analyzedGames.length >= 2) {
          const userProducts: Record<string, EngineProduct> = {}

          const productsToGen = product && PRODUCT_IDS.includes(product)
            ? [product]
            : PRODUCT_IDS.filter(k => !product || k === product)

          for (const prodId of productsToGen) {
            const picks = generateUserParlays(analyzedGames, userId, prodId, today)
            const isML = prodId.includes('parlay-ml')
            // Transform engine fields → UI fields
            const uiPicks = picks.map((pick: any) => ({
              ...pick,
              combined_confidence: pick.combined_prob ? pick.combined_prob * 100 : 0,
              games: (pick.games || []).map((g: any) => {
                if (isML || pick.pick_mode === 'moneyline') {
                  return {
                    home_team: g.home || g.home_team || '',
                    away_team: g.away || g.away_team || '',
                    game_date: g.game_date || '',
                    game_time: g.game_time || '',
                    predicted_winner: g.ml_pick || g.pick || '',
                    confidence: g.ml_prob ? g.ml_prob * 100 : (g.confidence ?? 0),
                    home_probability: g.ml_home_prob || 0,
                    away_probability: g.ml_away_prob || 0,
                    bet_type: 'moneyline',
                    bet_label: 'ML',
                  }
                }
                const { home_probability, away_probability } = computeHomAwayProb(g)
                return {
                  home_team: g.home || g.home_team || '',
                  away_team: g.away || g.away_team || '',
                  game_date: g.game_date || '',
                  game_time: g.game_time || '',
                  predicted_winner: g.pick_type === 'spread'
                    ? `${g.pick || ''} ${g.spread_str || 'ATS'}`
                    : (g.pick || g.predicted_winner || ''),
                  confidence: gameConf(g) * 100,
                  home_probability,
                  away_probability,
                  bet_type: g.pick_type || 'spread',
                  bet_label: g.pick_type === 'spread' ? `ATS ${g.spread_str || ''}` : 'ML',
                  spread: g.spread,
                  pick_spread: g.pick_spread,
                  spread_str: g.spread_str,
                }
              }),
            }))

            userProducts[prodId] = {
              product_name: prodId.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
              date: today,
              generated_at: new Date().toISOString(),
              picks: uiPicks,
              total_picks: uiPicks.length,
            }
          }

          if (Object.keys(userProducts).length > 0) {
            let data = userProducts
            if (preview) {
              const limited: Record<string, EngineProduct> = {}
              for (const [key, prod] of Object.entries(data)) {
                limited[key] = {
                  ...prod,
                  picks: prod.picks.slice(0, 2).map((pick) => ({
                    ...pick,
                    games: pick.games.map((g, i) =>
                      i === 0 ? g : { ...g, confidence: 0, predicted_winner: 'LOCKED' }
                    ),
                  })),
                }
              }
              data = limited
            }
            return NextResponse.json({
              picks: data,
              metadata: {
                date: today,
                generated_at: new Date().toISOString(),
                source: 'per_user_engine',
                user_id: userId,
                sportsbook: sportsbook || 'all',
                total_products: Object.keys(data).length,
                preview,
                timestamp: new Date().toISOString(),
              },
            })
          }
        }
      } catch {
        // Fall through to default engine data
      }
    }

    // If live=true or no engine file, generate from live odds
    let engineData: Record<string, EngineProduct> | null = null

    // Try Turso first (works on Vercel where local files don't exist)
    try {
      const today = new Date().toISOString().split('T')[0]
      const tursoGames = await fetchGamesFromTurso(today)
      if (tursoGames && tursoGames.length > 0) {
        // Generate default parlays from Turso data for non-user requests
        const defaultUserId = 'preview_default'
        const defaultProducts: Record<string, EngineProduct> = {}
        for (const prodId of PRODUCT_IDS) {
          const picks = generateUserParlays(tursoGames, defaultUserId, prodId, today)
          const uiPicks = picks.map((pick: any) => ({
            ...pick,
            combined_confidence: pick.combined_prob ? pick.combined_prob * 100 : 0,
            games: (pick.games || []).map((g: any) => {
              const { home_probability, away_probability } = computeHomAwayProb(g)
              return {
                home_team: g.home || g.home_team || '',
                away_team: g.away || g.away_team || '',
                game_date: g.game_date || '',
                game_time: g.game_time || '',
                predicted_winner: g.pick_type === 'spread'
                  ? `${g.pick || ''} ${g.spread_str || 'ATS'}`
                  : (g.pick || g.predicted_winner || ''),
                confidence: gameConf(g) * 100,
                home_probability,
                away_probability,
                bet_type: g.pick_type || 'spread',
                bet_label: g.pick_type === 'spread' ? `ATS ${g.spread_str || ''}` : 'ML',
                spread: g.spread,
                pick_spread: g.pick_spread,
                spread_str: g.spread_str,
              }
            }),
          }))
          defaultProducts[prodId] = {
            product_name: prodId.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
            date: today,
            generated_at: new Date().toISOString(),
            picks: uiPicks,
            total_picks: uiPicks.length,
          }
        }
        if (Object.keys(defaultProducts).length > 0) {
          engineData = defaultProducts
        }
      }
    } catch {
      // Turso not available, fall through to local file
    }

    // Fallback: try local file
    if (!engineData) try {
      const raw = await fs.readFile(PICKS_FILE, 'utf-8')
      const parsed = JSON.parse(raw)
      // Normalize engine field names to what PickCard expects
      engineData = {} as Record<string, EngineProduct>
      for (const [key, prod] of Object.entries(parsed) as [string, any][]) {
        engineData[key] = {
          ...prod,
          picks: (prod.picks || []).map((pick: any) => ({
            ...pick,
            games: (pick.games || []).map((g: any) => {
              const { home_probability, away_probability } = computeHomAwayProb(g)
              return {
                home_team: g.home_team || g.home || '',
                away_team: g.away_team || g.away || '',
                game_date: g.game_date || '',
                game_time: g.game_time || '',
                predicted_winner: g.pick_type === 'spread' || g.spread_str
                  ? `${g.pick || g.predicted_winner || ''} ${g.spread_str || 'ATS'}`
                  : (g.predicted_winner || g.pick || ''),
                confidence: gameConf(g) * 100,
                home_probability,
                away_probability,
                bet_type: g.pick_type || 'spread',
                bet_label: g.spread_str ? `ATS ${g.spread_str}` : (g.pick_type === 'spread' ? 'ATS' : 'ML'),
                spread: g.spread,
                pick_spread: g.pick_spread,
                spread_str: g.spread_str,
              }
            }),
            combined_confidence: pick.combined_confidence ?? (pick.combined_prob ? pick.combined_prob * 100 : 0),
            bet_type: 'spread',
          })),
        }
      }
    } catch {
      // No engine file
    }

    // REMOVED: Live odds fallback. ALL picks must come from engine analysis (Turso or local JSON).
    // If engine hasn't run yet for today, users see "no picks yet" instead of unvetted odds-only picks.

    if (!engineData) {
      return NextResponse.json({
        picks: {},
        metadata: {
          date: new Date().toISOString().split('T')[0],
          source: 'none',
          message: 'No picks generated yet for today. Check back closer to game time.',
          timestamp: new Date().toISOString(),
        },
      })
    }

    let data = engineData
    if (product && engineData[product]) {
      data = { [product]: engineData[product] }
    }

    if (preview) {
      const limited: Record<string, EngineProduct> = {}
      for (const [key, prod] of Object.entries(data)) {
        limited[key] = {
          ...prod,
          picks: prod.picks.slice(0, 2).map((pick) => ({
            ...pick,
            games: pick.games.map((g, i) =>
              i === 0 ? g : { ...g, confidence: 0, predicted_winner: 'LOCKED' }
            ),
          })),
        }
      }
      data = limited
    }

    const allGames = Object.values(engineData).flatMap((p) =>
      p.picks.flatMap((pick) => pick.games)
    )
    const avgConfidence =
      allGames.length > 0
        ? allGames.reduce((s, g) => s + (g.confidence || 0), 0) / allGames.length
        : 0

    // Try to load DFS data
    let dfsData = null
    try {
      const dfsRaw = await fs.readFile(DFS_FILE, 'utf-8')
      dfsData = JSON.parse(dfsRaw)
    } catch {
      // DFS data not available
    }

    return NextResponse.json({
      picks: data,
      dfs_lineups: dfsData,
      metadata: {
        date: Object.values(engineData)[0]?.date || new Date().toISOString().split('T')[0],
        generated_at: Object.values(engineData)[0]?.generated_at || null,
        source: 'engine_v2',
        total_products: Object.keys(engineData).length,
        total_games_analyzed: allGames.length,
        avg_confidence: Math.round(avgConfidence * 10) / 10,
        factors_analyzed: 37,
        preview,
        timestamp: new Date().toISOString(),
        engine_only: true,
        dfs_available: dfsData !== null,
      },
    })
  } catch (error) {
    console.error('Error fetching picks:', error)
    return NextResponse.json({ error: 'Failed to fetch picks' }, { status: 500 })
  }
}
