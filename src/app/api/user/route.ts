import { NextRequest, NextResponse } from 'next/server'
import jwt from 'jsonwebtoken'
import { initializeDatabase, getOrCreateUser, markFreePackUsed, useReferralCredit, getReferralCount } from '../../../../engine/db'

const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-here'

function getSession(request: NextRequest): any | null {
  try {
    const cookie = request.cookies.get('parlayguarantee-session')
    if (!cookie) return null
    const decoded = jwt.verify(cookie.value, JWT_SECRET) as any
    return decoded.type === 'session' ? decoded : null
  } catch {
    return null
  }
}

export async function GET(request: NextRequest) {
  const session = getSession(request)
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })
  }

  try {
    // Initialize database if needed
    await initializeDatabase()
    
    // Use async Turso functions
    const user = await getOrCreateUser(session.email)
    const referralCount = await getReferralCount(user.referral_code)
    
    return NextResponse.json({
      email: user.email,
      fullName: session.fullName || '',
      free_pack_available: !user.free_pack_used,
      free_pack_used: !!user.free_pack_used,
      referral_code: user.referral_code,
      referral_credits: user.referral_credits,
      referral_count: referralCount,
      packs_purchased: user.packs_purchased,
      created_at: user.created_at,
    })
  } catch (dbErr) {
    console.error('Database error:', dbErr)
    
    // JWT fallback (in case of database issues)
    return NextResponse.json({
      email: session.email,
      fullName: session.fullName || '',
      free_pack_available: !session.freePackUsed,
      free_pack_used: !!session.freePackUsed,
      referral_code: null,
      referral_credits: 0,
      referral_count: 0,
      packs_purchased: 0,
      created_at: null,
      error: 'Database temporarily unavailable'
    }, { status: 503 })
  }
}

export async function POST(request: NextRequest) {
  const session = getSession(request)
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })
  }

  const body = await request.json()

  if (body.action === 'use_free_pack') {
    try {
      await initializeDatabase()
      await markFreePackUsed(session.email)
      
      // Update JWT to mark free pack as used
      const newPayload = { ...session, freePackUsed: true }
      delete newPayload.iat // remove old iat so jwt.sign creates new one
      const newToken = jwt.sign(newPayload, JWT_SECRET)

      const response = NextResponse.json({ success: true, message: 'Free pack marked as used' })
      response.headers.set('Set-Cookie', `parlayguarantee-session=${newToken}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${7 * 24 * 60 * 60}`)
      return response
    } catch (dbErr) {
      console.error('Database error marking free pack used:', dbErr)
      
      // Update JWT anyway as fallback
      const newPayload = { ...session, freePackUsed: true }
      delete newPayload.iat
      const newToken = jwt.sign(newPayload, JWT_SECRET)

      const response = NextResponse.json({ success: true, message: 'Free pack marked as used (fallback)', warning: 'Database unavailable' })
      response.headers.set('Set-Cookie', `parlayguarantee-session=${newToken}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${7 * 24 * 60 * 60}`)
      return response
    }
  }

  if (body.action === 'use_referral_credit') {
    try {
      await initializeDatabase()
      const used = await useReferralCredit(session.email)
      if (used) {
        return NextResponse.json({ success: true, message: 'Referral credit used' })
      } else {
        return NextResponse.json({ error: 'No referral credits available' }, { status: 400 })
      }
    } catch (dbErr) {
      console.error('Database error using referral credit:', dbErr)
      return NextResponse.json({ error: 'Database temporarily unavailable' }, { status: 503 })
    }
  }

  return NextResponse.json({ error: 'Unknown action' }, { status: 400 })
}