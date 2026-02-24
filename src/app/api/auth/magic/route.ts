import { NextRequest, NextResponse } from 'next/server'
import jwt from 'jsonwebtoken'
import crypto from 'crypto'
import { isDisposableEmail } from '../../../../lib/disposable-domains'
import { initializeDatabase, checkFingerprintAbuse, checkIPRateLimit, logSignupFingerprint } from '../../../../../engine/db'

const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-here'
const EMAIL_FROM = process.env.EMAIL_FROM || 'Parlay Guarantee <noreply@parlayguarantee.com>'

function hashIP(ip: string): string {
  return crypto.createHash('sha256').update(ip + 'pg-salt-2026').digest('hex').slice(0, 16)
}

function calculateAge(dob: string): number {
  const [y, m, d] = dob.split('-').map(Number)
  const today = new Date()
  const birthDate = new Date(y, m - 1, d)
  let age = today.getFullYear() - birthDate.getFullYear()
  const mo = today.getMonth() - birthDate.getMonth()
  if (mo < 0 || (mo === 0 && today.getDate() < birthDate.getDate())) age--
  return age
}

export async function POST(request: NextRequest) {
  try {
    const { email, fingerprint, fullName, phone, address, dob, redirect } = await request.json()

    if (!email || !email.includes('@')) {
      return NextResponse.json({ error: 'Valid email required' }, { status: 400 })
    }

    if (!fullName || !phone || !address || !dob) {
      return NextResponse.json({ error: 'All fields are required' }, { status: 400 })
    }

    if (!address.street || !address.city || !address.state || !address.zip) {
      return NextResponse.json({ error: 'Complete address is required' }, { status: 400 })
    }

    // Server-side age check
    const age = calculateAge(dob)
    if (age < 21) {
      return NextResponse.json({ 
        error: 'You must be 21 years or older to use this service.',
        ageError: true 
      }, { status: 400 })
    }

    // Check disposable email
    if (isDisposableEmail(email)) {
      return NextResponse.json({ error: 'Please use a permanent email address' }, { status: 400 })
    }

    // Get IP from headers
    const ip = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim()
      || request.headers.get('x-real-ip')
      || 'unknown'
    const ipHash = hashIP(ip)

    // Check IP rate limit + fingerprint abuse using async Turso functions
    let skipFreePack = false
    try {
      await initializeDatabase()
      
      if (await checkIPRateLimit(ipHash)) {
        return NextResponse.json({ error: 'Too many signups from this location' }, { status: 429 })
      }
      
      if (fingerprint) {
        skipFreePack = await checkFingerprintAbuse(fingerprint, email)
      }
      
      await logSignupFingerprint(email, fingerprint || '', ipHash, skipFreePack)
    } catch (dbErr) {
      console.warn('Database check failed, continuing with signup but skipping anti-abuse:', dbErr)
      // Continue with signup but skip free pack to be safe
      skipFreePack = true
    }

    // Generate magic token
    const magicToken = crypto.randomBytes(32).toString('hex')
    
    // Create JWT payload - include all user fields
    const payload = {
      email,
      magicToken,
      type: 'magic_link',
      fullName,
      phone,
      address,
      dob,
      skipFreePack,
      fingerprint: fingerprint || '',
      exp: Math.floor(Date.now() / 1000) + (15 * 60)
    }

    const token = jwt.sign(payload, JWT_SECRET)

    // Magic link URL
    const redirectParam = redirect ? `&redirect=${encodeURIComponent(redirect)}` : ''
    const magicUrl = `${process.env.NEXTAUTH_URL || 'http://localhost:3000'}/auth/verify?token=${token}${redirectParam}`

    // Email HTML
    const emailHtml = `
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Sign in to Parlay Guarantee</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #00FF87, #FFD700); padding: 30px; border-radius: 10px; text-align: center; margin-bottom: 30px;">
            <h1 style="color: #000; margin: 0; font-size: 28px;">🏀 Parlay Guarantee</h1>
            <p style="color: #000; margin: 10px 0 0 0; font-size: 16px;">AI-Powered Sports Picks</p>
        </div>
        
        <h2 style="color: #00FF87;">Welcome, ${fullName}!</h2>
        <p>Click the button below to verify your account and unlock your <strong>FREE first pack</strong>. This link will expire in 15 minutes.</p>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="${magicUrl}" 
               style="background: #00FF87; color: #000; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 18px; display: inline-block;">
                🔐 Verify & Unlock Free Pack
            </a>
        </div>
        
        <p style="color: #666; font-size: 14px;">
            If the button doesn't work, copy and paste this link into your browser:<br>
            <a href="${magicUrl}" style="color: #00FF87; word-break: break-all;">${magicUrl}</a>
        </p>
        
        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
        
        <p style="color: #999; font-size: 12px; text-align: center;">
            This email was sent to ${email}. If you didn't request this, you can safely ignore it.<br>
            <em>For entertainment purposes only. Not gambling advice. Must be 21+ to use.</em>
        </p>
    </body>
    </html>
    `

    // Send email via Resend
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${(process.env.RESEND_API_KEY || 're_NEHSMNdA_15YcCrPhJ71LzDbqNdTZw53Y').trim()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: EMAIL_FROM,
        to: [email],
        subject: '🔐 Your Parlay Guarantee sign-in link',
        html: emailHtml,
        text: `Welcome ${fullName}! Verify your account: ${magicUrl}\n\nThis link expires in 15 minutes.`,
      }),
    })

    if (!res.ok) {
      const err = await res.text()
      console.error('Resend error:', err)
      throw new Error(`Email send failed: ${err}`)
    }

    return NextResponse.json({ 
      success: true, 
      message: 'Magic link sent! Check your email to sign in.' 
    })

  } catch (error: any) {
    console.error('Magic link error:', error)
    return NextResponse.json({ 
      error: 'Failed to send magic link',
      detail: error?.message || String(error)
    }, { status: 500 })
  }
}