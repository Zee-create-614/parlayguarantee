import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import { promisify } from 'util'
import path from 'path'

const execAsync = promisify(exec)
const ENGINE_DIR = path.join(process.cwd(), 'engine')

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const sport = searchParams.get('sport') || 'basketball_nba'
    const minEdge = searchParams.get('min_edge') || '0.03'
    const gamesFile = searchParams.get('games_file') || 'analyzed_games.json'

    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
    const cmd = `${pythonCmd} moneyline_parlay.py --sport ${sport} --min-edge ${minEdge} --games-file ${gamesFile}`

    const { stdout, stderr } = await execAsync(cmd, {
      cwd: ENGINE_DIR,
      timeout: 60_000,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })

    // Parse JSON from stdout (skip logging lines)
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
    console.error('Moneyline parlay engine error:', error)
    return NextResponse.json(
      {
        error: 'Moneyline parlay engine failed',
        message: error.message,
        stderr: error.stderr?.slice(-500),
      },
      { status: 500 }
    )
  }
}
