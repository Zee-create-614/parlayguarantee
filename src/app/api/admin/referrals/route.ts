import { NextRequest, NextResponse } from 'next/server'
import { initializeDatabase, getReferralAnalytics } from '../../../../../engine/db'

export async function GET(request: NextRequest) {
  const password = request.nextUrl.searchParams.get('password')
  if (password !== 'parlay2026') {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    await initializeDatabase()
    const analytics = await getReferralAnalytics()
    return NextResponse.json(analytics)
  } catch (e: any) {
    console.error('Referral analytics error:', e)
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}