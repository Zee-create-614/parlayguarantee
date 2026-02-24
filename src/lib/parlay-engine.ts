/**
 * Shared parlay generation engine — single source of truth.
 * Used by both /api/picks and /api/checkout to ensure identical pick generation.
 */
import crypto from 'crypto'

// ─── Seeded PRNG (mulberry32) ───
export function mulberry32(seed: number) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = t + Math.imul(t ^ (t >>> 7), 61 | t) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function userSeed(userId: string, dateStr: string): number {
  const raw = `${userId}:${dateStr}:parlayguarantee`
  const hash = crypto.createHash('sha256').update(raw).digest('hex')
  return parseInt(hash.slice(0, 10), 16)
}

// ─── Time-window helpers ───
const PARLAY_BUFFER_MINUTES = 60

export function classifyGameWindow(game: any): string {
  const ct = game.commence_time || game.game_time
  if (!ct) return 'late'
  const dt = new Date(ct)
  if (isNaN(dt.getTime())) return 'late'
  const etHour = (dt.getUTCHours() - 5 + 24) % 24
  if (etHour >= 12 && etHour < 18) return 'early'
  return 'late'
}

export function isGameEligibleForParlay(game: any): boolean {
  const ct = game.commence_time
  if (!ct) return true
  const start = new Date(ct)
  if (isNaN(start.getTime())) return true
  const cutoff = new Date(Date.now() + PARLAY_BUFFER_MINUTES * 60_000)
  return start > cutoff
}

// ─── Confidence scoring ───
export function gameConf(g: any): number {
  const cp = g.cover_prob || 0.5
  const ep = g.enhanced_prob || cp
  const mp = g.ml_prob || 0.5
  if (cp < 0.52) {
    const mlContrib = Math.min(mp, 0.65)
    return 0.3 * cp + 0.4 * ep + 0.3 * mlContrib
  }
  return cp
}

export function computeHomAwayProb(g: any): { home_probability: number; away_probability: number } {
  const pick = g.pick || ''
  const home = g.home || g.home_team || ''
  const coverProb = gameConf(g)
  const pickIsHome = pick.toLowerCase() === home.toLowerCase()
  if (g.ml_home_prob && g.ml_away_prob) {
    return { home_probability: g.ml_home_prob, away_probability: g.ml_away_prob }
  }
  if (pickIsHome) {
    return { home_probability: coverProb, away_probability: 1 - coverProb }
  } else {
    return { home_probability: 1 - coverProb, away_probability: coverProb }
  }
}

// ─── Helpers ───
export function gameSport(g: any): string {
  const s = (g.sport || '').toLowerCase()
  if (s.includes('ncaa') || s.includes('cbb') || s.includes('college')) return 'ncaab'
  if (s.includes('nba')) return 'nba'
  if (s.includes('nhl')) return 'nhl'
  if (s.includes('mlb')) return 'mlb'
  if (s.includes('nfl')) return 'nfl'
  return s || 'unknown'
}

export function isSpreadPick(g: any): boolean {
  const pt = (g.pick_type || '').toLowerCase()
  return pt !== 'total' && pt !== 'over_under' && pt !== 'ou'
}

export function* combinations(n: number, k: number): Generator<number[]> {
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

export function isMixedSportCombo(games: any[]): boolean {
  const sports = new Set(games.map(gameSport))
  return sports.has('nba') && sports.has('ncaab')
}

// ─── Get count of eligible games (used by purchase-limits) ───
export async function getAvailableGameCount(sportFilter?: string): Promise<number> {
  const { getClient } = await import('../../engine/db')
  const { promises: fs } = await import('fs')
  const path = await import('path')

  const today = new Date().toISOString().split('T')[0]
  let games: any[] = []

  try {
    const client = getClient()
    const result = await client.execute({
      sql: 'SELECT * FROM daily_picks WHERE pick_date = ?',
      args: [today],
    })
    if (result.rows && result.rows.length > 0) {
      games = result.rows.map((row: any) => {
        if (row.raw_json) {
          try { return JSON.parse(row.raw_json) } catch {}
        }
        return { sport: row.sport, commence_time: row.commence_time, pick_type: row.pick_type || 'spread' }
      })
    }
  } catch {}

  if (games.length === 0) {
    try {
      const filePath = path.join(process.cwd(), 'engine', 'analyzed_games.json')
      const raw = await fs.readFile(filePath, 'utf-8')
      games = JSON.parse(raw)
    } catch { return 0 }
  }

  let eligible = games.filter(isSpreadPick).filter(isGameEligibleForParlay)
  if (sportFilter) {
    const sf = sportFilter.toLowerCase()
    eligible = eligible.filter(g => {
      const s = gameSport(g)
      return s === sf || (sf === 'mixed' && (s === 'nba' || s === 'ncaab'))
    })
  }
  return eligible.length
}

// ─── Convenience: generate a single unique parlay of N legs ───
// Used by dashboard and auth flows for free/bonus parlays.
export async function generateUniqueParlay(numLegs: number, userId?: string): Promise<any | null> {
  // Dynamic import to avoid circular deps with engine/db
  const { getClient } = await import('../../engine/db')
  const { promises: fs } = await import('fs')
  const path = await import('path')

  const today = new Date().toISOString().split('T')[0]
  let games: any[] = []

  try {
    const client = getClient()
    const result = await client.execute({
      sql: 'SELECT * FROM daily_picks WHERE pick_date = ?',
      args: [today],
    })
    if (result.rows && result.rows.length > 0) {
      games = result.rows.map((row: any) => {
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
  } catch {}

  if (games.length === 0) {
    try {
      const filePath = path.join(process.cwd(), 'engine', 'analyzed_games.json')
      const raw = await fs.readFile(filePath, 'utf-8')
      games = JSON.parse(raw)
    } catch { return null }
  }

  const parlays = generateUserParlays(games, userId || 'bonus_default', 'parlay-consistent', today)
  const match = parlays.find((p: any) => p.legs === numLegs)
  return match || null
}

// ─── Product IDs ───
export const PRODUCT_IDS = [
  'parlay-consistent',
  'parlay-moonshot',
  'parlay-mixed',
  'parlay-weekday',
  'parlay-weekend',
  'referral-bundle',
  'parlay-ml-safe',
  'parlay-ml-value',
]

// ─── Sportsbook name mapping (user-facing → Odds API key) ───
const SPORTSBOOK_MAP: Record<string, string> = {
  'DraftKings': 'draftkings',
  'draftkings': 'draftkings',
  'FanDuel': 'fanduel',
  'fanduel': 'fanduel',
  'BetMGM': 'betmgm',
  'betmgm': 'betmgm',
  'Caesars': 'caesars',
  'caesars': 'caesars',
  'PointsBet': 'pointsbet',
  'pointsbet': 'pointsbet',
  'BetRivers': 'betrivers',
  'betrivers': 'betrivers',
}

function filterGamesBySportsbook(games: any[], sportsbook?: string): any[] {
  if (!sportsbook || sportsbook === 'Other' || sportsbook === 'other' || sportsbook === 'all') return games
  const key = SPORTSBOOK_MAP[sportsbook] || sportsbook.toLowerCase()
  return games.filter(g => {
    const bk = g.bookmakers || ''
    if (!bk) return true  // no bookmaker data = include by default
    return bk.split(',').some((b: string) => b.trim() === key)
  })
}

// ─── Overlap checker ───
function overlapFraction(a: number[], b: number[]): number {
  let shared = 0
  for (const x of a) if (b.includes(x)) shared++
  return shared / Math.max(a.length, b.length)
}

// ─── Shuffle top portion of array using seeded RNG ───
function seededShuffle(arr: any[], rng: () => number): any[] {
  const out = [...arr]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

// ─── Main generation function ───
export function generateUserParlays(
  analyzedGames: any[],
  userId: string,
  productMix: string,
  dateStr: string,
  sportsbook?: string,
  purchaseIndex: number = 0,
): any[] {
  const eligible = filterGamesBySportsbook(
    analyzedGames.filter(isSpreadPick).filter(isGameEligibleForParlay),
    sportsbook
  )

  if (eligible.length < 2) return []

  const seed = userSeed(userId, dateStr) + purchaseIndex * 7919
  const pool = [...eligible].sort((a, b) => gameConf(b) - gameConf(a))
  const nbaGames = pool.filter(g => gameSport(g) === 'nba')
  const ncaabGames = pool.filter(g => gameSport(g) === 'ncaab')
  const hasBothSports = nbaGames.length > 0 && ncaabGames.length > 0
  const n = pool.length

  // ML parlay products
  const isMLProduct = productMix.includes('parlay-ml')
  const isMLSafe = productMix === 'parlay-ml-safe'
  const isMLValue = productMix === 'parlay-ml-value'

  if (isMLProduct) {
    const mlPool = filterGamesBySportsbook(
      analyzedGames.filter(isGameEligibleForParlay).filter((g: any) => g.ml_pick && g.ml_prob > 0.55),
      sportsbook
    ).sort((a: any, b: any) => (b.ml_prob || 0) - (a.ml_prob || 0))

    if (mlPool.length < 2) return []

    const mlLimits: Record<number, number> = isMLSafe
      ? { 2: 15, 3: 10 }
      : { 3: 12, 4: 8, 5: 5 }

    const mlParlays: any[] = []
    let mlPickNum = 0
    const mlN = mlPool.length

    for (const k of Object.keys(mlLimits).map(Number).filter(k => k <= mlN)) {
      const limit = mlLimits[k] || 5
      const topN = Math.min(mlN, k <= 3 ? 30 : 20)
      const topPool = mlPool.slice(0, topN)
      const allCombos: { prob: number; indices: number[] }[] = []

      for (const combo of combinations(topN, k)) {
        let prob = 1
        for (let ii = 0; ii < combo.length; ii++) prob *= (topPool[combo[ii]].ml_prob || 0.5)
        allCombos.push({ prob, indices: combo })
        if (allCombos.length >= limit * 5) break
      }

      allCombos.sort((a, b) => b.prob - a.prob)
      const rng = mulberry32(seed + k * 2000 + purchaseIndex * 4391)
      const candidates = allCombos.slice(0, limit * 4)
      for (const c of candidates) c.prob += (rng() - 0.5) * 0.10
      candidates.sort((a, b) => b.prob - a.prob)

      const mlSelectedIndices: number[][] = []
      for (const c of candidates) {
        if (mlSelectedIndices.length >= limit) break
        const tooSimilar = mlSelectedIndices.some(prev => overlapFraction(c.indices, prev) > 0.5)
        if (tooSimilar) continue
        mlSelectedIndices.push(c.indices)
      }

      for (const idxSet of mlSelectedIndices) {
        const c = { indices: idxSet, prob: 1 }
        for (const i of idxSet) c.prob *= (topPool[i].ml_prob || 0.5)
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

  // Spread-based products
  const isMoonshot = productMix.includes('moonshot')
  const isConsistent = productMix.includes('consistent')

  const limits: Record<number, number> = isConsistent
    ? { 2: 25, 3: 15, 4: 8, 5: 4, 6: 2, 7: 2, 8: 1 }
    : isMoonshot
    ? { 2: 20, 3: 15, 4: 10, 5: 5, 6: 3, 7: 2, 8: 1 }
    : { 2: 20, 3: 12, 4: 8, 5: 4, 6: 2, 7: 2, 8: 1 }

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

  const legCounts = Object.keys(limits).map(Number).filter(k => k <= n)

  for (const k of legCounts) {
    const limit = limits[k] || 5

    // Use top 80% of pool for diverse selection
    const topN = Math.min(n, Math.max(k + 2, Math.ceil(n * 0.8)))
    const rng = mulberry32(seed + k * 1000 + purchaseIndex * 3571)
    // Shuffle the pool for this leg count to get genuinely different combos
    const shuffledPool = seededShuffle(pool.slice(0, topN), mulberry32(seed + k * 1337 + purchaseIndex * 5003))

    if (k >= 4 && hasBothSports) {
      const mixedCombos: { prob: number; indices: number[] }[] = []

      for (const combo of combinations(topN, k)) {
        const games = combo.map(i => shuffledPool[i])
        if (!isMixedSportCombo(games)) continue
        let prob = 1
        for (const g of games) prob *= gameConf(g)
        mixedCombos.push({ prob, indices: combo })
        if (mixedCombos.length >= limit * 10) break
      }

      mixedCombos.sort((a, b) => b.prob - a.prob)
      // Apply meaningful perturbation (±0.05)
      const candidates = mixedCombos.slice(0, limit * 4)
      for (const c of candidates) c.prob += (rng() - 0.5) * 0.10
      candidates.sort((a, b) => b.prob - a.prob)

      // Select with max 50% overlap enforcement
      const selectedIndices: number[][] = []
      for (const c of candidates) {
        if (selectedIndices.length >= limit) break
        const tooSimilar = selectedIndices.some(prev => overlapFraction(c.indices, prev) > 0.5)
        if (tooSimilar) continue
        selectedIndices.push(c.indices)
        parlays.push(buildParlay(c.indices.map(i => shuffledPool[i]), true))
      }
    } else {
      const allCombos: { prob: number; indices: number[] }[] = []

      for (const combo of combinations(topN, k)) {
        let prob = 1
        for (const i of combo) prob *= gameConf(shuffledPool[i])
        allCombos.push({ prob, indices: combo })
        if (allCombos.length >= limit * 10) break
      }

      allCombos.sort((a, b) => b.prob - a.prob)
      // Apply meaningful perturbation (±0.05)
      const candidates = allCombos.slice(0, limit * 4)
      for (const c of candidates) c.prob += (rng() - 0.5) * 0.10
      candidates.sort((a, b) => b.prob - a.prob)

      // Select with max 50% overlap enforcement
      const selectedIndices: number[][] = []
      for (const c of candidates) {
        if (selectedIndices.length >= limit) break
        const tooSimilar = selectedIndices.some(prev => overlapFraction(c.indices, prev) > 0.5)
        if (tooSimilar) continue
        selectedIndices.push(c.indices)
        parlays.push(buildParlay(c.indices.map(i => shuffledPool[i])))
      }
    }
  }

  return parlays
}
