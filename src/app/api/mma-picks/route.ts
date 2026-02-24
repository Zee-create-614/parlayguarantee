import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import { promisify } from 'util'
import path from 'path'
import fs from 'fs/promises'

const execAsync = promisify(exec)
const ENGINE_DIR = path.join(process.cwd(), 'engine')
const CACHE_FILE = path.join(ENGINE_DIR, 'mma_picks_cache.json')
const CACHE_TTL_MS = 60 * 60 * 1000 // 1 hour

interface CachedResult {
  timestamp: number
  data: any
}

async function getCachedPicks(): Promise<CachedResult | null> {
  try {
    const raw = await fs.readFile(CACHE_FILE, 'utf-8')
    const cached: CachedResult = JSON.parse(raw)
    if (Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return cached
    }
  } catch {
    // no cache or expired
  }
  return null
}

async function runEngine(date?: string): Promise<any> {
  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
  const dateArg = date ? `--date ${date}` : ''
  const cmd = `${pythonCmd} mma_engine.py --picks ${dateArg} --output mma_picks_output.json`

  const { stdout, stderr } = await execAsync(cmd, {
    cwd: ENGINE_DIR,
    timeout: 180_000, // 3 minutes (scraping can be slow)
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  })

  // Read the output file
  const outputPath = path.join(ENGINE_DIR, 'mma_picks_output.json')
  const data = JSON.parse(await fs.readFile(outputPath, 'utf-8'))

  // Cache it
  const cached: CachedResult = { timestamp: Date.now(), data }
  await fs.writeFile(CACHE_FILE, JSON.stringify(cached), 'utf-8')

  return data
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const date = searchParams.get('date') || undefined
    const noCache = searchParams.get('nocache') === '1'

    // Check cache first (unless date filter or nocache)
    if (!date && !noCache) {
      const cached = await getCachedPicks()
      if (cached) {
        const picks = cached.data.picks || []
        return NextResponse.json({
          success: true,
          cached: true,
          generated_at: cached.data.generated_at,
          model_version: cached.data.model_version || '2.0-32factor',
          straight_picks: picks.filter((p: any) => p.type === 'straight'),
          parlays: picks.filter((p: any) => p.type === 'parlay'),
          total_picks: picks.filter((p: any) => p.type === 'straight').length,
          total_parlays: picks.filter((p: any) => p.type === 'parlay').length,
        })
      }
    }

    // Run engine
    const data = await runEngine(date)
    const picks = data.picks || []

    return NextResponse.json({
      success: true,
      cached: false,
      generated_at: data.generated_at,
      model_version: data.model_version || '2.0-32factor',
      straight_picks: picks.filter((p: any) => p.type === 'straight'),
      parlays: picks.filter((p: any) => p.type === 'parlay'),
      total_picks: picks.filter((p: any) => p.type === 'straight').length,
      total_parlays: picks.filter((p: any) => p.type === 'parlay').length,
    })
  } catch (error: any) {
    console.error('MMA picks engine error:', error)
    return NextResponse.json(
      {
        error: 'MMA engine failed',
        message: error.message,
        stderr: error.stderr?.slice(-500),
      },
      { status: 500 }
    )
  }
}
