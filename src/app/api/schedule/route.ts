import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'

const SCHEDULE_FILE = path.join(process.cwd(), 'engine', 'weekly_schedule.json')

interface GameEntry {
  game_date: string
  home_team: string
  away_team: string
  game_id: string
  game_status: string
  game_time: string
}

interface WeeklySchedule {
  week_start: string
  week_end: string
  fetched_at: string
  games: GameEntry[]
  games_by_day: Record<string, GameEntry[]>
}

export async function GET(request: NextRequest) {
  try {
    let schedule: WeeklySchedule | null = null

    try {
      const raw = await fs.readFile(SCHEDULE_FILE, 'utf-8')
      schedule = JSON.parse(raw)
    } catch {
      // File not found or invalid — that's fine
    }

    if (!schedule || !schedule.games || schedule.games.length === 0) {
      return NextResponse.json({
        schedule: null,
        metadata: {
          message: 'No weekly schedule available. Engine needs to run with --mode schedule first.',
          timestamp: new Date().toISOString(),
        },
      })
    }

    // Group by day with day names
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    const grouped: Record<string, { day_name: string; date: string; games: GameEntry[] }> = {}

    for (const game of schedule.games) {
      const dateKey = game.game_date
      if (!grouped[dateKey]) {
        const d = new Date(dateKey + 'T12:00:00')
        grouped[dateKey] = {
          day_name: dayNames[d.getUTCDay()],
          date: dateKey,
          games: [],
        }
      }
      grouped[dateKey].games.push(game)
    }

    // Sort by date
    const days = Object.values(grouped).sort((a, b) => a.date.localeCompare(b.date))

    return NextResponse.json({
      schedule: {
        week_start: schedule.week_start,
        week_end: schedule.week_end,
        fetched_at: schedule.fetched_at,
        total_games: schedule.games.length,
        days,
      },
      metadata: {
        timestamp: new Date().toISOString(),
      },
    })
  } catch (error) {
    console.error('Error fetching schedule:', error)
    return NextResponse.json({ error: 'Failed to fetch schedule' }, { status: 500 })
  }
}
