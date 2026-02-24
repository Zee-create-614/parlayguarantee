import { NextRequest, NextResponse } from 'next/server'
import jwt from 'jsonwebtoken'
import { saveBettingConfig } from '../../../../lib/kv'

const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-here'

export async function POST(req: NextRequest) {
  try {
    const { paymentIntentId, sportsbook, betAmountPerPick, tier, sports } = await req.json()

    if (!sportsbook || !betAmountPerPick || betAmountPerPick <= 0) {
      return NextResponse.json({ error: 'Sportsbook and bet amount required' }, { status: 400 })
    }

    // Get email from session
    let email = ''
    const cookie = req.cookies.get('parlayguarantee-session')
    if (cookie) {
      try {
        const decoded = jwt.verify(cookie.value, JWT_SECRET) as any
        email = decoded.email || ''
      } catch {}
    }

    await saveBettingConfig(email || paymentIntentId || 'anonymous', {
      paymentIntentId,
      sportsbook,
      betAmountPerPick,
      tier: tier || null,
      sports: sports || null,
    })

    return NextResponse.json({ success: true })
  } catch (error: any) {
    console.error('Error saving betting config:', error)
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
