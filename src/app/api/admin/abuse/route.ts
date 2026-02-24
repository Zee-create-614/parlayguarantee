import { NextRequest, NextResponse } from 'next/server'
import { getAbuseReport } from '../../../../../engine/db'

const ADMIN_PASSWORD = 'parlay2026'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const password = searchParams.get('password')

  if (password !== ADMIN_PASSWORD) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    const report = getAbuseReport()
    return NextResponse.json(report)
  } catch (error) {
    console.error('Abuse report error:', error)
    return NextResponse.json({ error: 'Failed to generate report' }, { status: 500 })
  }
}
