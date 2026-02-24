import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'
import { logReferralClick } from '../../../../engine/db'

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get('code')
  if (!code) {
    return NextResponse.redirect(new URL('/', request.url))
  }

  try {
    const forwarded = request.headers.get('x-forwarded-for') || 'unknown'
    const ip = forwarded.split(',')[0].trim()
    const ipHash = crypto.createHash('sha256').update(ip).digest('hex').slice(0, 16)
    const userAgent = request.headers.get('user-agent') || 'unknown'

    logReferralClick(code, ipHash, userAgent)
  } catch (e) {
    console.error('Failed to log referral click:', e)
  }

  return NextResponse.redirect(new URL(`/?ref=${code}`, request.url))
}
