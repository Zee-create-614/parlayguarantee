// Parlay Engine - Live Odds Version
// Fetches real data from The Odds API via /api/odds

export type Sport = 'nba' | 'nfl' | 'mlb' | 'nhl' | 'ufc' | 'soccer' | 'ncaab' | 'ncaaf'

export interface Game {
  id: string
  sport: Sport
  homeTeam: string
  awayTeam: string
  startTime: string
  status: 'scheduled' | 'live' | 'completed'
  venue?: string
}

export interface LiveOddsEvent {
  id: string
  sport: Sport
  homeTeam: string
  awayTeam: string
  startTime: string
  status: 'scheduled'
  moneyline: { home: number; away: number }
  spread: { home: number; away: number; homeOdds: number; awayOdds: number }
  total: { over: number; under: number; overOdds: number; underOdds: number }
  bookmaker: string
}

export interface Odds {
  gameId: string
  spread: { home: number; away: number; odds: number }
  total: { over: number; under: number; overOdds: number; underOdds: number }
  moneyline: { home: number; away: number }
}

export interface PlayerProp {
  gameId: string
  playerId: string
  playerName: string
  team: string
  props: {
    [key: string]: { line: number; overOdds: number; underOdds: number } | { odds: number }
  }
}

export interface ParlayLeg {
  gameId: string
  sport: Sport
  team: string
  bet: string
  odds: number
  line: number | null // spread point (e.g. +3.5), total line (e.g. 220.5), or null for ML
  type: 'spread' | 'total' | 'moneyline' | 'player_prop' | 'fight_method' | 'rounds'
  homeTeam?: string
  awayTeam?: string
}

export type ParlayWindow = 'early' | 'late' | 'full_slate'

export interface Parlay {
  id: number
  sport?: Sport
  legs: ParlayLeg[]
  combinedOdds: string
  confidence: number
  expectedValue: number
  teams: string[]
  window?: ParlayWindow
  windowLabel?: string
  payout: {
    bet10: number
    bet25: number
    bet50: number
    bet100: number
  }
}

// ---- Time Window Logic ----
// Buffer: games must start at least this many minutes after now
const BUFFER_MINUTES = 15

function classifyWindow(startTimeISO: string): ParlayWindow {
  const dt = new Date(startTimeISO)
  // Convert to ET (UTC-5)
  const etHour = (dt.getUTCHours() - 5 + 24) % 24
  if (etHour >= 12 && etHour < 18) return 'early'
  return 'late'
}

function windowLabel(w: ParlayWindow): string {
  const labels: Record<ParlayWindow, string> = {
    early: 'Early Window (12-6 PM ET)',
    late: 'Late Window (6 PM+ ET)',
    full_slate: 'Full Slate',
  }
  return labels[w] || w
}

function isGameEligible(event: LiveOddsEvent): boolean {
  const cutoff = new Date(Date.now() + BUFFER_MINUTES * 60_000)
  const start = new Date(event.startTime)
  return start > cutoff
}

function groupEventsByWindow(events: LiveOddsEvent[]): Record<ParlayWindow, LiveOddsEvent[]> {
  const eligible = events.filter(isGameEligible)
  const groups: Record<ParlayWindow, LiveOddsEvent[]> = { early: [], late: [], full_slate: [] }
  for (const ev of eligible) {
    const w = classifyWindow(ev.startTime)
    groups[w].push(ev)
  }
  // full_slate = all eligible if there are games in both windows
  if (groups.early.length > 0 && groups.late.length > 0) {
    groups.full_slate = [...groups.early, ...groups.late]
  } else if (groups.early.length === 0) {
    groups.full_slate = [...groups.late]
  }
  return groups
}

// American odds to decimal
export function americanToDecimal(americanOdds: number): number {
  if (americanOdds > 0) return americanOdds / 100 + 1
  return 100 / Math.abs(americanOdds) + 1
}

// Combined parlay odds
export function calculateParlayOdds(legs: ParlayLeg[]): { decimal: number; american: string } {
  const decimalOdds = legs.reduce((acc, leg) => acc * americanToDecimal(leg.odds), 1)
  const americanOdds =
    decimalOdds >= 2
      ? Math.round((decimalOdds - 1) * 100)
      : Math.round(-100 / (decimalOdds - 1))
  return {
    decimal: decimalOdds,
    american: americanOdds > 0 ? `+${americanOdds}` : americanOdds.toString(),
  }
}

export function calculatePayouts(americanOdds: string, betAmounts: number[]): number[] {
  const odds = parseInt(americanOdds.replace('+', ''))
  return betAmounts.map((bet) => {
    if (odds > 0) return +(bet + (bet * odds) / 100).toFixed(2)
    return +(bet + (bet * 100) / Math.abs(odds)).toFixed(2)
  })
}

// ---------- Live data fetching ----------

const ODDS_API_KEY = (process.env.ODDS_API_KEY || 'f3c9f91dc369f56dea1b523d3071e1f1').trim()
const ODDS_BASE_URL = 'https://api.the-odds-api.com/v4'

const SPORT_KEY_MAP: Record<string, string> = {
  nba: 'basketball_nba',
  nhl: 'icehockey_nhl',
  mlb: 'baseball_mlb',
  ufc: 'mma_mixed_martial_arts',
  soccer: 'soccer_epl',
  ncaab: 'basketball_ncaab',
}

const REVERSE_SPORT_MAP: Record<string, string> = {
  basketball_nba: 'nba',
  icehockey_nhl: 'nhl',
  baseball_mlb: 'mlb',
  mma_mixed_martial_arts: 'ufc',
  soccer_epl: 'soccer',
  basketball_ncaab: 'ncaab',
}

// In-memory cache for server-side
let oddsCache: { data: LiveOddsEvent[]; timestamp: number } | null = null
const ODDS_CACHE_TTL = 5 * 60 * 1000

function parseOddsEvent(event: any): LiveOddsEvent | null {
  const book = event.bookmakers?.[0]
  if (!book) return null
  const markets: Record<string, any[]> = {}
  for (const m of book.markets || []) markets[m.key] = m.outcomes

  const h2h = markets.h2h || []
  const spreads = markets.spreads || []
  const totals = markets.totals || []

  const homeH2h = h2h.find((o: any) => o.name === event.home_team)
  const awayH2h = h2h.find((o: any) => o.name === event.away_team)
  const homeSpread = spreads.find((o: any) => o.name === event.home_team)
  const awaySpread = spreads.find((o: any) => o.name === event.away_team)
  const over = totals.find((o: any) => o.name === 'Over')
  const under = totals.find((o: any) => o.name === 'Under')

  return {
    id: event.id,
    sport: (REVERSE_SPORT_MAP[event.sport_key] || event.sport_key) as Sport,
    homeTeam: event.home_team,
    awayTeam: event.away_team,
    startTime: event.commence_time,
    status: 'scheduled',
    moneyline: { home: homeH2h?.price ?? 0, away: awayH2h?.price ?? 0 },
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
    bookmaker: book.title || 'N/A',
  }
}

async function fetchLiveEvents(sport?: Sport): Promise<LiveOddsEvent[]> {
  // Try direct Odds API call (works reliably on Vercel serverless)
  if (typeof window === 'undefined') {
    // Check cache
    if (oddsCache && Date.now() - oddsCache.timestamp < ODDS_CACHE_TTL) {
      const cached = oddsCache.data
      return sport ? cached.filter(e => e.sport === sport) : cached
    }

    const sportKeys = sport
      ? [SPORT_KEY_MAP[sport]].filter(Boolean)
      : ['basketball_nba', 'basketball_ncaab'] // Only fetch working sports

    const allEvents: LiveOddsEvent[] = []
    const results = await Promise.allSettled(
      sportKeys.map(async (sk) => {
        const url = `${ODDS_BASE_URL}/sports/${sk}/odds/?apiKey=${ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals&oddsFormat=american`
        const res = await fetch(url)
        if (!res.ok) { console.error(`Odds API ${sk}: ${res.status}`); return [] }
        const events = await res.json()
        return (events as any[]).map(parseOddsEvent).filter(Boolean) as LiveOddsEvent[]
      })
    )
    for (const r of results) {
      if (r.status === 'fulfilled') allEvents.push(...r.value)
    }

    oddsCache = { data: allEvents, timestamp: Date.now() }
    return sport ? allEvents.filter(e => e.sport === sport) : allEvents
  }

  // Client-side: use internal API
  const url = sport ? `/api/odds?sport=${sport}` : `/api/odds`
  const res = await fetch(url, { next: { revalidate: 300 } })
  if (!res.ok) return []
  const json = await res.json()
  return json.events || []
}

export async function fetchGames(sport?: Sport): Promise<Game[]> {
  const events = await fetchLiveEvents(sport)
  return events.map((e) => ({
    id: e.id,
    sport: e.sport as Sport,
    homeTeam: e.homeTeam,
    awayTeam: e.awayTeam,
    startTime: e.startTime,
    status: e.status,
  }))
}

export async function fetchOdds(sport?: Sport): Promise<Odds[]> {
  const events = await fetchLiveEvents(sport)
  return events.map((e) => ({
    gameId: e.id,
    spread: { home: e.spread.home, away: e.spread.away, odds: e.spread.homeOdds },
    total: e.total,
    moneyline: e.moneyline,
  }))
}

// ---------- Parlay generation from live odds ----------

function buildLeg(event: LiveOddsEvent, betType: 'moneyline' | 'spread' | 'total', side: 'home' | 'away' | 'over' | 'under'): ParlayLeg | null {
  if (betType === 'moneyline') {
    const isHome = side === 'home'
    const team = isHome ? event.homeTeam : event.awayTeam
    const odds = isHome ? event.moneyline.home : event.moneyline.away
    if (!odds) return null
    return { gameId: event.id, sport: event.sport as Sport, team, bet: `Moneyline ${team}`, odds, line: null, type: 'moneyline', homeTeam: event.homeTeam, awayTeam: event.awayTeam }
  }
  if (betType === 'spread') {
    const isHome = side === 'home'
    const team = isHome ? event.homeTeam : event.awayTeam
    const point = isHome ? event.spread.home : event.spread.away
    const odds = isHome ? event.spread.homeOdds : event.spread.awayOdds
    if (!point && point !== 0) return null
    const sign = point > 0 ? '+' : ''
    return { gameId: event.id, sport: event.sport as Sport, team, bet: `Spread ${sign}${point}`, odds, line: point, type: 'spread', homeTeam: event.homeTeam, awayTeam: event.awayTeam }
  }
  if (betType === 'total') {
    const isOver = side === 'over'
    const line = event.total.over || event.total.under
    if (!line) return null
    const odds = isOver ? event.total.overOdds : event.total.underOdds
    return {
      gameId: event.id,
      sport: event.sport as Sport,
      team: `${event.homeTeam} vs ${event.awayTeam}`,
      bet: `${isOver ? 'Over' : 'Under'} ${line}`,
      odds,
      line,
      type: 'total',
      homeTeam: event.homeTeam,
      awayTeam: event.awayTeam,
    }
  }
  return null
}

// Simple confidence heuristic: favor slight favorites, moderate totals
function legConfidence(leg: ParlayLeg): number {
  const dec = americanToDecimal(leg.odds)
  // Implied probability
  const impliedProb = 1 / dec
  // Convert to 0-100 confidence, capped
  return Math.min(95, Math.max(40, impliedProb * 100 + (Math.random() * 10 - 5)))
}

export async function generateParlays(numPicks: number = 10, sport?: Sport): Promise<Parlay[]> {
  const events = await fetchLiveEvents(sport)
  if (events.length === 0) return []

  // Group events by time window (only eligible games)
  const windowGroups = groupEventsByWindow(events)

  // Build leg pools per window
  const buildLegsForEvents = (evts: LiveOddsEvent[]): ParlayLeg[] => {
    const pool: ParlayLeg[] = []
    for (const ev of evts) {
      const candidates: [('moneyline' | 'spread' | 'total'), ('home' | 'away' | 'over' | 'under')][] = [
        ['moneyline', 'home'], ['moneyline', 'away'],
        ['spread', 'home'], ['spread', 'away'],
        ['total', 'over'], ['total', 'under'],
      ]
      for (const [bt, side] of candidates) {
        const leg = buildLeg(ev, bt, side)
        if (leg && leg.odds !== 0) pool.push(leg)
      }
    }
    return pool
  }

  const shuffle = <T,>(arr: T[]): T[] => {
    const a = [...arr]
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[a[i], a[j]] = [a[j], a[i]]
    }
    return a
  }

  const parlays: Parlay[] = []
  const legCounts = [2, 2, 3, 3, 4, 2, 3, 4, 5, 6]

  // Generate parlays per window — ensures all legs are placeable together
  const windowOrder: ParlayWindow[] = ['late', 'early', 'full_slate']
  let parlayIdx = 0

  for (const windowName of windowOrder) {
    const windowEvents = windowGroups[windowName]
    if (!windowEvents || windowEvents.length === 0) continue

    const legPool = buildLegsForEvents(windowEvents)
    if (legPool.length < 2) continue

    // Allocate picks proportionally
    const picksForWindow = Math.max(2, Math.round(numPicks / windowOrder.filter(w => (windowGroups[w]?.length || 0) > 0).length))

    for (let i = 0; i < picksForWindow && parlayIdx < numPicks; i++) {
      const targetLegs = legCounts[parlayIdx % legCounts.length]
      const shuffled = shuffle(legPool)

      const usedGames = new Set<string>()
      const selectedLegs: ParlayLeg[] = []
      for (const leg of shuffled) {
        if (usedGames.has(leg.gameId)) continue
        selectedLegs.push(leg)
        usedGames.add(leg.gameId)
        if (selectedLegs.length >= targetLegs) break
      }

      if (selectedLegs.length < 2) continue

      const { decimal, american } = calculateParlayOdds(selectedLegs)
      const [p10, p25, p50, p100] = calculatePayouts(american, [10, 25, 50, 100])

      const avgConf = selectedLegs.reduce((s, l) => s + legConfidence(l), 0) / selectedLegs.length
      const ev = (avgConf / 100) * decimal - 1

      const sports = [...new Set(selectedLegs.map((l) => l.sport))]
      const parlaySport = sports.length === 1 ? sports[0] : undefined

      parlays.push({
        id: parlayIdx + 1,
        sport: parlaySport,
        legs: selectedLegs,
        combinedOdds: american,
        confidence: Math.round(avgConf),
        expectedValue: +ev.toFixed(2),
        window: windowName,
        windowLabel: windowLabel(windowName),
        teams: selectedLegs.map((l) =>
          l.type === 'total' ? l.team : `${l.team} (${l.sport.toUpperCase()})`
        ),
        payout: { bet10: p10, bet25: p25, bet50: p50, bet100: p100 },
      })
      parlayIdx++
    }
  }

  parlays.sort((a, b) => b.confidence - a.confidence)
  return parlays.slice(0, numPicks)
}

// ---------- Engine Picks Loader ----------

interface EngineLeg {
  game: string
  pick: string
  type: string
  line: string
  prob: number
  sport: string
  commence_time: string
}

interface EnginePick {
  legs: EngineLeg[]
  combined_prob: number
  payout_odds: string
  leg_count: number
}

async function loadEnginePicks(): Promise<{ tiers: Record<string, { picks: EnginePick[] }>, ml_tiers?: Record<string, { picks: EnginePick[] }> } | null> {
  if (typeof window !== 'undefined') return null
  try {
    const fs = await import('fs')
    const path = await import('path')
    const filePath = path.join(process.cwd(), 'engine', 'picks_output.json')
    const data = await fs.promises.readFile(filePath, 'utf-8')
    return JSON.parse(data)
  } catch {
    return null
  }
}

function engineLegToParlay(eLeg: EngineLeg): ParlayLeg & { confidence: number; pickId: string } {
  // Parse "Dallas Mavericks @ Indiana Pacers" format
  const parts = eLeg.game.split(' @ ')
  const awayTeam = parts[0]?.trim() || ''
  const homeTeam = parts[1]?.trim() || ''
  
  // Determine odds from probability
  const prob = eLeg.prob
  let odds: number
  if (prob >= 0.5) {
    odds = Math.round(-100 * prob / (1 - prob))
  } else {
    odds = Math.round(100 * (1 - prob) / prob)
  }

  const line = eLeg.line ? parseFloat(eLeg.line) : null
  const betType = eLeg.type?.toLowerCase() || 'spread'
  const sign = line && line > 0 ? '+' : ''
  const betLabel = betType === 'moneyline' 
    ? `Moneyline ${eLeg.pick}` 
    : betType === 'total'
    ? `${eLeg.pick} ${line}`
    : `Spread ${sign}${line}`

  const gameId = `${awayTeam}_${homeTeam}_${eLeg.commence_time}`.replace(/\s/g, '_')
  const pickId = `engine_${gameId}_${betType}_${eLeg.pick.replace(/\s/g, '_')}`

  return {
    gameId,
    sport: (eLeg.sport?.toLowerCase() || 'nba') as Sport,
    team: eLeg.pick,
    bet: betLabel,
    odds,
    line,
    type: betType as 'moneyline' | 'spread' | 'total',
    homeTeam,
    awayTeam,
    confidence: Math.round(prob * 100),
    pickId,
  }
}

// ---------- N-Leg Parlay Generation for Tier System ----------

/**
 * Generate a unique N-leg parlay using ENGINE picks first.
 * Falls back to Odds API only if engine picks unavailable.
 * 
 * @param numLegs - Number of legs (1-7)
 * @param sport - Optional sport filter
 * @param excludePickIds - Pick IDs already assigned to this user today
 * @param tierPriority - Higher number = access to better picks (2-leg=1, 6-leg=5)
 */
export async function generateUniqueParlay(
  numLegs: number,
  sport?: Sport,
  excludePickIds: string[] = [],
  tierPriority: number = 1,
  preferredWindow?: ParlayWindow,
  betTypeFilter?: 'moneyline' | 'spread' | 'total',
): Promise<Parlay | null> {

  // ========== STEP 1: Try engine picks first ==========
  const engineData = await loadEnginePicks()
  if (engineData) {
    const isML = betTypeFilter === 'moneyline'
    const tierKey = isML
      ? (numLegs === 1 ? 'ml-single' : `ml-${numLegs}leg`)
      : (numLegs === 1 ? 'single' : `${numLegs}leg`)
    
    const tierSource = isML ? engineData.ml_tiers : engineData.tiers
    const tierData = tierSource?.[tierKey]
    
    if (tierData?.picks?.length) {
      // Collect all engine legs from all picks in this tier, filter by sport
      const allEngineLegs: (ParlayLeg & { confidence: number; pickId: string })[] = []
      
      for (const pick of tierData.picks) {
        for (const eLeg of pick.legs) {
          // Sport filter
          const legSport = (eLeg.sport?.toLowerCase() || 'nba') as Sport
          if (sport && sport !== 'nba' && sport !== 'ncaab') continue // unknown sport
          if (sport && legSport !== sport) continue
          
          const converted = engineLegToParlay(eLeg)
          if (!excludePickIds.includes(converted.pickId)) {
            allEngineLegs.push(converted)
          }
        }
      }
      
      // Sort by confidence (engine probability) descending
      allEngineLegs.sort((a, b) => b.confidence - a.confidence)
      
      // Select from different games
      const usedGames = new Set<string>()
      const selectedLegs: (ParlayLeg & { confidence: number; pickId: string })[] = []
      
      for (const leg of allEngineLegs) {
        if (usedGames.has(leg.gameId)) continue
        selectedLegs.push(leg)
        usedGames.add(leg.gameId)
        if (selectedLegs.length >= numLegs) break
      }
      
      if (selectedLegs.length >= numLegs) {
        const { decimal, american } = calculateParlayOdds(selectedLegs)
        const [p10, p25, p50, p100] = calculatePayouts(american, [10, 25, 50, 100])
        const avgConf = selectedLegs.reduce((s, l) => s + l.confidence, 0) / selectedLegs.length
        const ev = (avgConf / 100) * decimal - 1
        const sports = [...new Set(selectedLegs.map((l) => l.sport))]

        return {
          id: Date.now(),
          sport: sports.length === 1 ? sports[0] : undefined,
          legs: selectedLegs,
          combinedOdds: american,
          confidence: Math.round(avgConf),
          expectedValue: +ev.toFixed(2),
          window: 'late',
          windowLabel: windowLabel('late'),
          teams: selectedLegs.map((l) =>
            l.type === 'total' ? l.team : `${l.team} (${l.sport.toUpperCase()})`
          ),
          payout: { bet10: p10, bet25: p25, bet50: p50, bet100: p100 },
          _pickIds: selectedLegs.map(l => l.pickId),
        } as Parlay & { _pickIds: string[] }
      }
    }
  }

  // ========== STEP 2: Fallback to Odds API if engine picks unavailable ==========
  console.log('[parlay-engine] Engine picks unavailable or insufficient, falling back to Odds API')
  
  const events = await fetchLiveEvents(sport)
  if (events.length < numLegs) return null

  const eligibleEvents = events.filter(isGameEligible)
  if (eligibleEvents.length < numLegs) return null

  let targetEvents = eligibleEvents
  if (preferredWindow && preferredWindow !== 'full_slate') {
    const windowed = eligibleEvents.filter(ev => classifyWindow(ev.startTime) === preferredWindow)
    if (windowed.length >= numLegs) {
      targetEvents = windowed
    }
  }

  const allLegs: (ParlayLeg & { confidence: number; pickId: string })[] = []
  for (const ev of targetEvents) {
    let candidates: [('moneyline' | 'spread' | 'total'), ('home' | 'away' | 'over' | 'under')][]
    if (betTypeFilter === 'moneyline') {
      candidates = [['moneyline', 'home'], ['moneyline', 'away']]
    } else if (betTypeFilter === 'spread') {
      candidates = [['spread', 'home'], ['spread', 'away']]
    } else if (betTypeFilter === 'total') {
      candidates = [['total', 'over'], ['total', 'under']]
    } else if (numLegs === 1) {
      candidates = [['moneyline', 'home'], ['moneyline', 'away']]
    } else {
      candidates = [
        ['moneyline', 'home'], ['moneyline', 'away'],
        ['spread', 'home'], ['spread', 'away'],
        ['total', 'over'], ['total', 'under'],
      ]
    }
    for (const [bt, side] of candidates) {
      const leg = buildLeg(ev, bt, side)
      if (leg && leg.odds !== 0) {
        const pickId = `${ev.id}_${bt}_${side}`
        if (!excludePickIds.includes(pickId)) {
          allLegs.push({ ...leg, confidence: legConfidence(leg), pickId })
        }
      }
    }
  }

  allLegs.sort((a, b) => b.confidence - a.confidence)

  const usedGames = new Set<string>()
  const selectedLegs: (ParlayLeg & { confidence: number; pickId: string })[] = []
  for (const leg of allLegs) {
    if (usedGames.has(leg.gameId)) continue
    selectedLegs.push(leg)
    usedGames.add(leg.gameId)
    if (selectedLegs.length >= numLegs) break
  }

  if (selectedLegs.length < numLegs) return null

  const { decimal, american } = calculateParlayOdds(selectedLegs)
  const [p10, p25, p50, p100] = calculatePayouts(american, [10, 25, 50, 100])
  const avgConf = selectedLegs.reduce((s, l) => s + l.confidence, 0) / selectedLegs.length
  const ev = (avgConf / 100) * decimal - 1
  const sports = [...new Set(selectedLegs.map((l) => l.sport))]

  return {
    id: Date.now(),
    sport: sports.length === 1 ? sports[0] : undefined,
    legs: selectedLegs,
    combinedOdds: american,
    confidence: Math.round(avgConf),
    expectedValue: +ev.toFixed(2),
    window: preferredWindow || 'late',
    windowLabel: windowLabel(preferredWindow || 'late'),
    teams: selectedLegs.map((l) =>
      l.type === 'total' ? l.team : `${l.team} (${l.sport.toUpperCase()})`
    ),
    payout: { bet10: p10, bet25: p25, bet50: p50, bet100: p100 },
    _pickIds: selectedLegs.map(l => l.pickId),
  } as Parlay & { _pickIds: string[] }
}

/**
 * Get the number of available games for a sport (used to disable tiers).
 */
export async function getAvailableGameCount(sport?: Sport): Promise<number> {
  const events = await fetchLiveEvents(sport)
  return events.filter(isGameEligible).length
}

export async function fetchPlayerStats(sport?: Sport): Promise<PlayerProp[]> {
  // Player props require a separate API tier — return empty for now
  return []
}

export async function evaluateResults(
  parlayId: number,
  finalScores: any[]
): Promise<{ win: boolean; legsWon: number; totalLegs: number; payout: number }> {
  // TODO: implement with real score data
  return { win: false, legsWon: 0, totalLegs: 0, payout: 0 }
}
