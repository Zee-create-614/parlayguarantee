import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'
import crypto from 'crypto'
// generateParlays/fetchGames removed — all picks must come from engine analysis only
import { getClient, initializeDatabase } from '../../../../engine/db'

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

// ---- Per-user parlay generation (TypeScript port of user_parlay_generator.py) ----

function userSeed(userId: string, dateStr: string): number {
  const raw = `${userId}:${dateStr}:parlayguarantee`
  const hash = crypto.createHash('sha256').update(raw).digest('hex')
  return parseInt(hash.slice(0, 10), 16) // 10 hex chars → safe 40-bit int
}

// Simple seeded PRNG (mulberry32)
function mulberry32(seed: number) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = t + Math.imul(t ^ (t >>> 7), 61 | t) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// Time-window helpers for user parlay generation
const PARLAY_BUFFER_MINUTES = 60

function classifyGameWindow(game: any): string {
  const ct = game.commence_time || game.game_time
  if (!ct) return 'late'
  // Try ISO parse first
  const dt = new Date(ct)
  if (isNaN(dt.getTime())) return 'late'
  const etHour = (dt.getUTCHours() - 5 + 24) % 24
  if (etHour >= 12 && etHour < 18) return 'early'
  return 'late'
}

function isGameEligibleForParlay(game: any): boolean {
  const ct = game.commence_time
  if (!ct) return true // no time data, allow it (legacy)
  const start = new Date(ct)
  if (isNaN(start.getTime())) return true
  const cutoff = new Date(Date.now() + PARLAY_BUFFER_MINUTES * 60_000)
  return start > cutoff
}

function groupGamesByWindow(games: any[]): Record<string, any[]> {
  const eligible = games.filter(isGameEligibleForParlay)
  const groups: Record<string, any[]> = { early: [], late: [] }
  for (const g of eligible) {
    const w = classifyGameWindow(g)
    if (w === 'early') groups.early.push(g)
    else groups.late.push(g)
  }
  return groups
}

// Helper: get confidence value for a game (spread-based)
// Blend cover_prob with enhanced_prob and ml_prob for meaningful differentiation
function gameConf(g: any): number {
  const cp = g.cover_prob || 0.5
  const ep = g.enhanced_prob || cp
  const mp = g.ml_prob || 0.5
  // If cover_prob is essentially a coin flip (<0.52), blend with better signals
  if (cp < 0.52) {
    // Weight: 30% cover_prob, 40% enhanced_prob, 30% ml_prob (capped contribution)
    const mlContrib = Math.min(mp, 0.65) // cap ML so huge favorites don't dominate
    return 0.3 * cp + 0.4 * ep + 0.3 * mlContrib
  }
  return cp
}

// Helper: compute home/away probabilities from engine fields
function computeHomAwayProb(g: any): { home_probability: number; away_probability: number } {
  const pick = g.pick || ''
  const home = g.home || g.home_team || ''
  const coverProb = gameConf(g)
  const pickIsHome = pick.toLowerCase() === home.toLowerCase()

  // Use ML probs if available (they're actually populated)
  if (g.ml_home_prob && g.ml_away_prob) {
    return { home_probability: g.ml_home_prob, away_probability: g.ml_away_prob }
  }

  // Derive from cover_prob based on which team is picked
  if (pickIsHome) {
    return { home_probability: coverProb, away_probability: 1 - coverProb }
  } else {
    return { home_probability: 1 - coverProb, away_probability: coverProb }
  }
}

// Helper: get sport for a game
function gameSport(g: any): string {
  const s = (g.sport || '').toLowerCase()
  if (s.includes('ncaa') || s.includes('cbb') || s.includes('college')) return 'ncaab'
  if (s.includes('nba')) return 'nba'
  if (s.includes('nhl')) return 'nhl'
  if (s.includes('mlb')) return 'mlb'
  if (s.includes('nfl')) return 'nfl'
  return s || 'unknown'
}

// Helper: is this a spread pick (NOT total/O-U)
function isSpreadPick(g: any): boolean {
  const pt = (g.pick_type || '').toLowerCase()
  return pt !== 'total' && pt !== 'over_under' && pt !== 'ou'
}

// Generate all k-combinations from array (indices)
function* combinations(n: number, k: number): Generator<number[]> {
  if (k > n) return
  const indices = Array.from({ length: k }, (_, i) => i)
  yield [...indices]
  while (true) {
    let i = k - 1
    while (i >= 0 && indices[i] === i + n - k) i--
    if (i < 0) return
    indices[i]++
    for (let j = i + 1; j < k; j++) indices[j] = indices[j - 1] + 1
    yield [...indices]
  }
}

// Check if a combo includes both NBA and NCAAB
function isMixedSportCombo(games: any[]): boolean {
  const sports = new Set(games.map(gameSport))
  return sports.has('nba') && sports.has('ncaab')
}

function generateUserParlays(
  analyzedGames: any[],
  userId: string,
  productMix: string, // now a product ID string, not number[]
  dateStr: string
): any[] {
  // Filter to spread picks only (NO O/U) and eligible games
  const eligible = analyzedGames
    .filter(isSpreadPick)
    .filter(isGameEligibleForParlay)
  
  if (eligible.length < 2) return []

  const seed = userSeed(userId, dateStr)
  
  // Sort by confidence descending
  const pool = [...eligible].sort((a, b) => gameConf(b) - gameConf(a))
  
  const nbaGames = pool.filter(g => gameSport(g) === 'nba')
  const ncaabGames = pool.filter(g => gameSport(g) === 'ncaab')
  const hasBothSports = nbaGames.length > 0 && ncaabGames.length > 0
  
  const n = pool.length

  // ML parlay products — use ML fields instead of spread
  const isMLProduct = productMix.includes('parlay-ml')
  const isMLSafe = productMix === 'parlay-ml-safe'
  const isMLValue = productMix === 'parlay-ml-value'

  if (isMLProduct) {
    // Filter to games with ML data and good probability
    const mlPool = analyzedGames
      .filter(isGameEligibleForParlay)
      .filter((g: any) => g.ml_pick && g.ml_prob > 0.55)
      .sort((a: any, b: any) => (b.ml_prob || 0) - (a.ml_prob || 0))

    if (mlPool.length < 2) return []

    const mlLimits: Record<number, number> = isMLSafe
      ? { 2: 15, 3: 10 }  // safe: 2-3 legs, high prob favorites
      : { 3: 12, 4: 8, 5: 5 }  // value: 3-5 legs, edge picks

    const mlParlays: any[] = []
    let mlPickNum = 0
    const n = mlPool.length

    for (const k of Object.keys(mlLimits).map(Number).filter(k => k <= n)) {
      const limit = mlLimits[k] || 5
      const topN = Math.min(n, k <= 3 ? 30 : 20)
      const topPool = mlPool.slice(0, topN)
      const allCombos: { prob: number; indices: number[] }[] = []

      for (const combo of combinations(topN, k)) {
        let prob = 1
        for (let ii = 0; ii < combo.length; ii++) prob *= (topPool[combo[ii]].ml_prob || 0.5)
        allCombos.push({ prob, indices: combo })
        if (allCombos.length >= limit * 5) break
      }

      allCombos.sort((a, b) => b.prob - a.prob)
      const rng = mulberry32(seed + k * 2000)
      const candidates = allCombos.slice(0, limit * 2)
      for (const c of candidates) c.prob += (rng() - 0.5) * 0.001
      candidates.sort((a, b) => b.prob - a.prob)

      for (const c of candidates.slice(0, limit)) {
        const games = c.indices.map(i => topPool[i])
        let combinedProb = 1
        for (const g of games) combinedProb *= (g.ml_prob || 0.5)
        const payout = combinedProb > 0 ? 1 / combinedProb : 1
        mlPickNum++

        mlParlays.push({
          pick_number: mlPickNum,
          type: 'parlay',
          pick_mode: 'moneyline',
          legs: games.length,
          games,
          combined_prob: Math.round(combinedProb * 10000) / 10000,
          implied_payout: `${payout.toFixed(1)}x`,
        })
      }
    }

    return mlParlays
  }

  // Dynamic limits based on product type and available games
  const isMoonshot = productMix.includes('moonshot')
  const isConsistent = productMix.includes('consistent')
  
  // Determine how many parlays to generate per leg count
  const limits: Record<number, number> = isConsistent
    ? { 2: 25, 3: 15, 4: 8, 5: 4, 6: 2 }
    : isMoonshot
    ? { 2: 20, 3: 15, 4: 10, 5: 5, 6: 3, 7: 2, 8: 1 }
    : { 2: 20, 3: 12, 4: 8, 5: 4, 6: 2 } // default/mixed/weekday/weekend

  const parlays: any[] = []
  let pickNum = 0

  const windowLabels: Record<string, string> = {
    early: 'Early Window (12-6 PM ET)',
    late: 'Late Window (6 PM+ ET)',
    full_slate: 'Full Slate',
  }

  function buildParlay(games: any[], forceMixedLabel: boolean = false) {
    let combinedProb = 1
    for (const g of games) combinedProb *= gameConf(g)
    const payout = combinedProb > 0 ? 1 / combinedProb : 1

    const gameTimes = games.map((g: any) => g.game_time || g.commence_time).filter(Boolean)
    const earliestGameTime = gameTimes.length ? gameTimes.sort()[0] : ''

    const commenceTimes = games.map((g: any) => g.commence_time).filter(Boolean)
    let parlayWindow = 'late'
    if (commenceTimes.length > 0) {
      const hasEarly = commenceTimes.some((ct: string) => {
        const h = (new Date(ct).getUTCHours() - 5 + 24) % 24
        return h >= 12 && h < 18
      })
      const hasLate = commenceTimes.some((ct: string) => {
        const h = (new Date(ct).getUTCHours() - 5 + 24) % 24
        return h >= 18 || h < 4
      })
      if (hasEarly && !hasLate) parlayWindow = 'early'
      else if (hasEarly && hasLate) parlayWindow = 'full_slate'
    }

    const isMixed = isMixedSportCombo(games)
    pickNum++

    return {
      pick_number: pickNum,
      type: 'parlay',
      legs: games.length,
      games,
      combined_prob: Math.round(combinedProb * 10000) / 10000,
      implied_payout: `${payout.toFixed(1)}x`,
      earliest_game_time: earliestGameTime,
      window: parlayWindow,
      window_label: windowLabels[parlayWindow] || parlayWindow,
      recommended: isMixed && games.length >= 4,
      mixed_sport: isMixed,
      mixed_label: isMixed ? 'Mixed Parlay (NBA + NCAAB) - Higher hit probability' : undefined,
    }
  }

  // For each leg count, generate top combos by combined confidence
  const legCounts = Object.keys(limits).map(Number).filter(k => k <= n)
  
  for (const k of legCounts) {
    const limit = limits[k] || 5
    
    if (k >= 4 && hasBothSports) {
      // 4+ legs: MUST be mixed sport (NBA + NCAAB)
      // Generate combos that include at least one from each sport
      const mixedCombos: { prob: number; indices: number[] }[] = []
      
      // Cap iteration for large pools — only consider top games
      const topN = Math.min(n, k <= 4 ? 30 : 20)
      const topPool = pool.slice(0, topN)
      
      for (const combo of combinations(topN, k)) {
        const games = combo.map(i => topPool[i])
        if (!isMixedSportCombo(games)) continue
        let prob = 1
        for (const g of games) prob *= gameConf(g)
        mixedCombos.push({ prob, indices: combo })
        // Collect enough candidates
        if (mixedCombos.length >= limit * 3) break
      }
      
      // Sort by combined probability descending, take top N
      mixedCombos.sort((a, b) => b.prob - a.prob)
      const topCombos = mixedCombos.slice(0, limit)
      
      // Deterministic user-specific selection: use seed to shuffle the top combos slightly
      const rng = mulberry32(seed + k * 1000)
      for (const c of topCombos) {
        c.prob += (rng() - 0.5) * 0.001 // tiny jitter for per-user uniqueness
      }
      topCombos.sort((a, b) => b.prob - a.prob)
      
      for (const c of topCombos.slice(0, limit)) {
        const topPoolLocal = pool.slice(0, Math.min(n, k <= 4 ? 30 : 20))
        parlays.push(buildParlay(c.indices.map(i => topPoolLocal[i]), true))
      }
    } else {
      // 2-3 legs (or 4+ when only one sport): generate by confidence ranking
      const allCombos: { prob: number; indices: number[] }[] = []
      
      const topN = Math.min(n, k <= 3 ? 35 : 25)
      const topPool = pool.slice(0, topN)
      
      for (const combo of combinations(topN, k)) {
        let prob = 1
        for (const i of combo) prob *= gameConf(topPool[i])
        allCombos.push({ prob, indices: combo })
        if (allCombos.length >= limit * 5) break
      }
      
      allCombos.sort((a, b) => b.prob - a.prob)
      
      // Per-user jitter
      const rng = mulberry32(seed + k * 1000)
      const candidates = allCombos.slice(0, limit * 2)
      for (const c of candidates) {
        c.prob += (rng() - 0.5) * 0.001
      }
      candidates.sort((a, b) => b.prob - a.prob)
      
      for (const c of candidates.slice(0, limit)) {
        const topPoolLocal = pool.slice(0, topN)
        parlays.push(buildParlay(c.indices.map(i => topPoolLocal[i])))
      }
    }
  }
  
  return parlays
}

// Product IDs — the generateUserParlays function dynamically determines
// parlay counts based on game availability + product type
const PRODUCT_IDS = [
  'parlay-consistent',
  'parlay-moonshot',
  'parlay-mixed',
  'parlay-weekday',
  'parlay-weekend',
  'referral-bundle',
  'parlay-ml-safe',
  'parlay-ml-value',
]

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
