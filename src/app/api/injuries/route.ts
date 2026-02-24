import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import { promisify } from 'util'
import path from 'path'
import fs from 'fs'

const execAsync = promisify(exec)
const ENGINE_DIR = path.join(process.cwd(), 'engine')
const CACHE_FILE = path.join(ENGINE_DIR, 'injury_cache.json')
const CACHE_TTL_MS = 30 * 60 * 1000 // 30 minutes

export async function GET(request: NextRequest) {
  try {
    const force = request.nextUrl.searchParams.get('force') === 'true'

    // Check if cached file is fresh enough
    if (!force && fs.existsSync(CACHE_FILE)) {
      try {
        const stat = fs.statSync(CACHE_FILE)
        const age = Date.now() - stat.mtimeMs
        if (age < CACHE_TTL_MS) {
          const cached = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf-8'))
          return NextResponse.json({
            ...cached,
            cached: true,
            cache_age_minutes: Math.round(age / 60000),
          })
        }
      } catch (e) {
        // Cache read failed, proceed to scrape
      }
    }

    // Run the Python scraper
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
    const cmd = `${pythonCmd} injury_scraper.py --json${force ? ' --force' : ''}`

    const { stdout, stderr } = await execAsync(cmd, {
      cwd: ENGINE_DIR,
      timeout: 30_000,
    })

    if (stderr) {
      console.warn('Injury scraper stderr:', stderr)
    }

    const data = JSON.parse(stdout)
    return NextResponse.json({ ...data, cached: false })
  } catch (error: unknown) {
    console.error('Injury API error:', error)

    // Try to return stale cache as fallback
    if (fs.existsSync(CACHE_FILE)) {
      try {
        const stale = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf-8'))
        return NextResponse.json({
          ...stale,
          cached: true,
          stale: true,
          error: 'Fresh data unavailable, returning cached',
        })
      } catch {}
    }

    return NextResponse.json(
      { error: 'Failed to fetch injury data', details: String(error) },
      { status: 500 }
    )
  }
}
