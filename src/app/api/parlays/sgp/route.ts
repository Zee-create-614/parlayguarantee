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
    const gamesFile = searchParams.get('games_file') || 'analyzed_games.json'
    const skipNbaApi = searchParams.get('fast') === 'true'

    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
    const flags = skipNbaApi ? '--no-nba-api' : ''
    const cmd = `${pythonCmd} sgp.py --sport ${sport} --games-file ${gamesFile} ${flags}`

    const { stdout, stderr } = await execAsync(cmd, {
      cwd: ENGINE_DIR,
      timeout: 120_000,
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
    console.error('SGP engine error:', error)
    return NextResponse.json(
      {
        error: 'SGP engine failed',
        message: error.message,
        stderr: error.stderr?.slice(-500),
      },
      { status: 500 }
    )
  }
}
