import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import { promisify } from 'util'
import path from 'path'

const execAsync = promisify(exec)

const ENGINE_DIR = path.join(process.cwd(), 'engine')
const OUTPUT_FILE = path.join(ENGINE_DIR, 'picks_output.json')

export async function POST(request: NextRequest) {
  try {
    // Verify secret key
    const authHeader = request.headers.get('authorization')
    const secret = process.env.ENGINE_SECRET
    if (!secret || authHeader !== `Bearer ${secret}`) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json().catch(() => ({}))
    const product = body.product || 'all'
    const date = body.date || new Date().toISOString().split('T')[0]

    // Run the Python engine
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
    const cmd = `${pythonCmd} engine_v2.py --product ${product} --date ${date} --output picks_output.json`

    const { stdout, stderr } = await execAsync(cmd, {
      cwd: ENGINE_DIR,
      timeout: 120_000, // 2 minute timeout
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })

    return NextResponse.json({
      success: true,
      product,
      date,
      output: stdout.trim().split('\n').slice(-5).join('\n'), // last 5 lines
      warnings: stderr ? stderr.trim().split('\n').slice(-3).join('\n') : null,
      output_file: OUTPUT_FILE,
      timestamp: new Date().toISOString(),
    })
  } catch (error: any) {
    console.error('Engine generation error:', error)
    return NextResponse.json(
      {
        error: 'Engine failed',
        message: error.message,
        stderr: error.stderr?.slice(-500),
      },
      { status: 500 }
    )
  }
}
