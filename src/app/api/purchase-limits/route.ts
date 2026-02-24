import { NextRequest, NextResponse } from 'next/server'
import jwt from 'jsonwebtoken'
import { getUserLimitsOverview } from '../../../lib/purchase-tracker'
import { getAvailableGameCount } from '../../../lib/parlay-engine'

const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-here'

export async function GET(request: NextRequest) {
  try {
    // Auth check
    const cookie = request.cookies.get('parlayguarantee-session')
    if (!cookie) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })
    }
    const decoded = jwt.verify(cookie.value, JWT_SECRET) as any
    if (!decoded.email) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })
    }

    const sport = request.nextUrl.searchParams.get('sport') || undefined
    const sportKey = sport?.toLowerCase().replace('ufc / mma', 'ufc').replace(/ /g, '') as any

    const [limits, gameCount] = await Promise.all([
      getUserLimitsOverview(decoded.email),
      getAvailableGameCount(sportKey),
    ])

    // Disable tiers that need more legs than available games
    const limitsWithAvailability = limits.map(l => ({
      ...l,
      disabled: gameCount < l.legs,
      disabledReason: gameCount < l.legs
        ? `Only ${gameCount} game${gameCount !== 1 ? 's' : ''} available — need ${l.legs}`
        : undefined,
    }))

    return NextResponse.json({
      limits: limitsWithAvailability,
      gameCount,
      sport: sport || 'all',
    })
  } catch (error: any) {
    console.error('Error fetching purchase limits:', error)
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
