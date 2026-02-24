import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import { promisify } from 'util'
import path from 'path'

const execAsync = promisify(exec)
const ENGINE_DIR = path.join(process.cwd(), 'engine')

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const action = searchParams.get('action') || 'summary'
    const sport = searchParams.get('sport') || 'basketball_nba'
    const daysBack = searchParams.get('days_back') || '30'
    const gamesFile = searchParams.get('games_file') || 'analyzed_games.json'

    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
    const cmd = `${pythonCmd} clv_tracker.py --action ${action} --sport ${sport} --days-back ${daysBack} --games-file ${gamesFile}`

    const { stdout, stderr } = await execAsync(cmd, {
      cwd: ENGINE_DIR,
      timeout: 60_000,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })

    const lines = stdout.trim().split('\n')
    let jsonStr = ''
    let inJson = false
    for (const line of lines) {
      if (line.startsWith('{')) inJson = true
      if (inJson) jsonStr += line + '\n'
    }

    const result = JSON.parse(jsonStr)
    return NextResponse.json(result)
  } catch (error: any) {
    console.error('CLV tracker error:', error)
    return NextResponse.json(
      {
        error: 'CLV tracker failed',
        message: error.message,
        stderr: error.stderr?.slice(-500),
      },
      { status: 500 }
    )
  }
}

// POST endpoint for storing opening odds (called by cron/engine at 3 PM)
export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization')
    const secret = process.env.ENGINE_SECRET
    if (secret && authHeader !== `Bearer ${secret}`) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json().catch(() => ({}))
    const action = body.action || 'store_opening'
    const sport = body.sport || 'basketball_nba'
    const gamesFile = body.games_file || 'analyzed_games.json'

    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
    const cmd = `${pythonCmd} clv_tracker.py --action ${action} --sport ${sport} --games-file ${gamesFile}`

    const { stdout, stderr } = await execAsync(cmd, {
      cwd: ENGINE_DIR,
      timeout: 60_000,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })

    const lines = stdout.trim().split('\n')
    let jsonStr = ''
    let inJson = false
    for (const line of lines) {
      if (line.startsWith('{')) inJson = true
      if (inJson) jsonStr += line + '\n'
    }

    const result = JSON.parse(jsonStr)
    return NextResponse.json(result)
  } catch (error: any) {
    console.error('CLV tracker POST error:', error)
    return NextResponse.json(
      {
        error: 'CLV tracker failed',
        message: error.message,
        stderr: error.stderr?.slice(-500),
      },
      { status: 500 }
    )
  }
}
