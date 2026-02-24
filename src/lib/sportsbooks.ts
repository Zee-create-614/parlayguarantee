// DB-driven sportsbook list stored in KV
// Key: 'config:sportsbooks'
// Value: array of { id: string, name: string, logo?: string, active: boolean }

import { Redis } from '@upstash/redis'

export interface Sportsbook {
  id: string      // e.g. 'draftkings', 'fanduel'
  name: string    // e.g. 'DraftKings', 'FanDuel'
  logo?: string   // optional emoji or URL
  active: boolean
}

const DEFAULT_SPORTSBOOKS: Sportsbook[] = [
  { id: 'draftkings', name: 'DraftKings', logo: '🟢', active: true },
  { id: 'fanduel', name: 'FanDuel', logo: '🔵', active: true },
  { id: 'betmgm', name: 'BetMGM', logo: '🟡', active: true },
  { id: 'caesars', name: 'Caesars', logo: '🏛️', active: true },
  { id: 'betrivers', name: 'BetRivers', logo: '🌊', active: true },
  { id: 'bovada', name: 'Bovada', logo: '🔴', active: true },
  { id: 'fanatics', name: 'Fanatics', logo: '⚡', active: true },
  { id: 'betonline', name: 'BetOnline', logo: '🎰', active: true },
  { id: 'betus', name: 'BetUS', logo: '🇺🇸', active: true },
  { id: 'other', name: 'Other', logo: '📱', active: true },
]

function getRedis(): Redis | null {
  const url = (process.env.UPSTASH_REDIS_REST_URL || '').trim()
  const token = (process.env.UPSTASH_REDIS_REST_TOKEN || '').trim()
  if (!url || !token) return null
  return new Redis({ url, token })
}

export async function getSportsbooks(): Promise<Sportsbook[]> {
  try {
    const r = getRedis()
    if (!r) return DEFAULT_SPORTSBOOKS.filter(s => s.active)
    const books = await r.get<Sportsbook[]>('config:sportsbooks')
    if (books && books.length > 0) return books.filter(s => s.active)
    // Seed default
    await r.set('config:sportsbooks', DEFAULT_SPORTSBOOKS)
    return DEFAULT_SPORTSBOOKS.filter(s => s.active)
  } catch {
    return DEFAULT_SPORTSBOOKS.filter(s => s.active)
  }
}

export async function updateSportsbooks(books: Sportsbook[]): Promise<void> {
  const r = getRedis()
  if (r) await r.set('config:sportsbooks', books)
}
