import { NextRequest, NextResponse } from 'next/server'
import jwt from 'jsonwebtoken'
import { cookies } from 'next/headers'
import { sendDripEmail } from '../../../../lib/email-drip'
import { createOrUpdateUser, saveFreePick, markFreePackUsedKV } from '../../../../lib/kv'
import { initializeDatabase, getOrCreateUser, useFreePackForUser } from '../../../../../engine/db'

const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-here'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const token = searchParams.get('token')
    const referredBy = searchParams.get('ref') || null

    if (!token) {
      return NextResponse.json({ error: 'Token required' }, { status: 400 })
    }

    let decoded: any
    try {
      decoded = jwt.verify(token, JWT_SECRET)
    } catch (error) {
      return NextResponse.json({ error: 'Invalid or expired token' }, { status: 401 })
    }

    if (decoded.type !== 'magic_link') {
      return NextResponse.json({ error: 'Invalid token type' }, { status: 401 })
    }

    // Create or update user using both Turso DB and KV for redundancy
    let isNewUser = true
    let freePackUsed = false

    // Try Turso database first
    try {
      await initializeDatabase()
      const user = await getOrCreateUser(decoded.email, referredBy)
      freePackUsed = user.free_pack_used
      isNewUser = !user.free_pack_used && !user.created_at // roughly detect if new
      
      if (decoded.skipFreePack) {
        await useFreePackForUser(decoded.email)
        freePackUsed = true
      }
    } catch (dbErr) {
      console.warn('Turso DB error, falling back to KV:', dbErr)
      
      // Fallback to KV
      try {
        const { user, isNew } = await createOrUpdateUser({
          email: decoded.email,
          fullName: decoded.fullName || '',
          phone: decoded.phone || '',
          address: decoded.address || null,
          dob: decoded.dob || '',
          referredBy: referredBy,
        })
        isNewUser = isNew
        freePackUsed = user.freePackUsed

        if (decoded.skipFreePack) {
          await markFreePackUsedKV(decoded.email)
          freePackUsed = true
        }
      } catch (kvErr) {
        console.warn('KV also failed, using stateless mode:', kvErr)
        freePackUsed = !!decoded.skipFreePack
      }
    }

    // Create session token
    const sessionPayload: any = {
      email: decoded.email,
      type: 'session',
      fullName: decoded.fullName || '',
      phone: decoded.phone || '',
      address: decoded.address || null,
      dob: decoded.dob || '',
      freePackUsed: freePackUsed,
      exp: Math.floor(Date.now() / 1000) + (7 * 24 * 60 * 60)
    }

    const sessionToken = jwt.sign(sessionPayload, JWT_SECRET)

    const response = NextResponse.json({ 
      success: true, 
      user: { email: decoded.email, fullName: decoded.fullName },
      message: 'Successfully signed in!'
    })

    response.headers.set('Set-Cookie', `parlayguarantee-session=${sessionToken}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${7 * 24 * 60 * 60}`)

    // Assign free signup pick using live odds engine (works on Vercel)
    if (!freePackUsed) {
      try {
        const { generateUniqueParlay } = await import('../../../../lib/parlay-engine')
        const parlay = await generateUniqueParlay(3) // 3-leg, any sport (NBA/NCAAB)
        if (parlay) {
          await saveFreePick(decoded.email, {
            sport: parlay.sport?.toUpperCase() || 'NBA',
            parlayData: parlay.legs.map(l => ({
              home_team: l.homeTeam || '',
              away_team: l.awayTeam || '',
              game_date: '',
              game_time: '',
              predicted_winner: l.team,
              confidence: parlay.confidence,
              home_probability: 0,
              away_probability: 0,
              bet_type: l.type,
              bet: l.bet,
              odds: l.odds,
              team: l.team,
            })),
            combinedOdds: parlay.combinedOdds || '',
            confidence: parlay.confidence || 0,
            status: 'pending',
          })
        } else {
          console.warn('No games available for free pick assignment')
        }
      } catch (fpErr) {
        console.warn('Free pick assignment failed:', fpErr)
      }
    }

    // Send welcome drip email (non-blocking)
    if (isNewUser) {
      sendDripEmail(decoded.email, 1).catch(err =>
        console.error('Failed to send welcome drip email:', err)
      );
    }

    return response

  } catch (error) {
    console.error('Magic link verification error:', error)
    return NextResponse.json({ error: 'Failed to verify magic link' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  return GET(request)
}