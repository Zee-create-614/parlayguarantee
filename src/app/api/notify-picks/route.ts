import { NextRequest, NextResponse } from 'next/server'

const ENGINE_SECRET = (process.env.ENGINE_SECRET || '').trim()
const RESEND_API_KEY = (process.env.RESEND_API_KEY || '').trim()
const FROM_EMAIL = 'Parlay Guarantee <noreply@parlayguarantee.com>'

// Try to load DB (won't work on Vercel serverless)
let getAllUsers: (() => any[]) | null = null
try {
  const dbModule = require('../../../../engine/db')
  const getDb = dbModule.getDb
  getAllUsers = () => {
    const db = getDb()
    return db.prepare(`
      SELECT u.email, u.free_pack_used, u.packs_purchased,
        (SELECT COUNT(*) FROM purchases WHERE email = u.email AND status = 'completed') as purchase_count
      FROM users u
    `).all()
  }
} catch {
  console.warn('DB not available (serverless)')
}

function activeUserEmail(gameCount: number): string {
  return `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:40px 20px;">
  <div style="text-align:center;margin-bottom:32px;">
    <h1 style="color:#22c55e;font-size:28px;margin:0;">🏀 Parlay Guarantee</h1>
  </div>
  <div style="background:#111;border:1px solid #1e1e1e;border-radius:12px;padding:32px;text-align:center;">
    <h2 style="color:#fff;font-size:24px;margin:0 0 16px;">Your AI Picks Are Ready</h2>
    <p style="color:#a1a1aa;font-size:16px;line-height:1.6;margin:0 0 24px;">
      Tonight's ${gameCount > 0 ? gameCount + '-game' : ''} NBA slate just dropped. Our 37-factor AI model has analyzed every matchup.
    </p>
    <a href="https://parlayguarantee.com/picks" style="display:inline-block;background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-size:16px;font-weight:600;">
      View Your Picks →
    </a>
  </div>
  <div style="text-align:center;margin-top:32px;padding-top:24px;border-top:1px solid #1e1e1e;">
    <p style="color:#52525b;font-size:12px;line-height:1.5;margin:0;">
      For entertainment purposes only. Must be 21+ to wager. Please gamble responsibly.<br>
      <a href="https://parlayguarantee.com" style="color:#52525b;">parlayguarantee.com</a>
    </p>
  </div>
</div>
</body>
</html>`
}

function marketingEmail(): string {
  return `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:40px 20px;">
  <div style="text-align:center;margin-bottom:32px;">
    <h1 style="color:#eab308;font-size:28px;margin:0;">🔥 Parlay Guarantee</h1>
  </div>
  <div style="background:#111;border:1px solid #1e1e1e;border-radius:12px;padding:32px;text-align:center;">
    <h2 style="color:#fff;font-size:24px;margin:0 0 16px;">Tonight's AI Picks Are In</h2>
    <p style="color:#a1a1aa;font-size:16px;line-height:1.6;margin:0 0 24px;">
      Our prediction engine just locked in tonight's slate. Don't miss out.
    </p>
    <a href="https://parlayguarantee.com/pricing" style="display:inline-block;background:linear-gradient(135deg,#eab308,#ca8a04);color:#000;text-decoration:none;padding:14px 32px;border-radius:8px;font-size:16px;font-weight:600;">
      View Pick Packages →
    </a>
  </div>
  <div style="text-align:center;margin-top:32px;padding-top:24px;border-top:1px solid #1e1e1e;">
    <p style="color:#52525b;font-size:12px;line-height:1.5;margin:0;">
      For entertainment purposes only. Must be 21+ to wager. Please gamble responsibly.<br>
      <a href="https://parlayguarantee.com" style="color:#52525b;">parlayguarantee.com</a>
    </p>
  </div>
</div>
</body>
</html>`
}

export async function POST(request: NextRequest) {
  // Auth check
  const secret = request.headers.get('x-engine-secret') || ''
  if (!ENGINE_SECRET || secret !== ENGINE_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  if (!RESEND_API_KEY) {
    return NextResponse.json({ error: 'RESEND_API_KEY not configured' }, { status: 500 })
  }

  // Parse body for game count (optional)
  let gameCount = 0
  try {
    const body = await request.json().catch(() => ({}))
    gameCount = body.gameCount || 0
  } catch {}

  // Get users from DB
  let users: any[] = []
  try {
    if (getAllUsers) {
      users = getAllUsers()
    }
  } catch (e) {
    console.warn('Failed to query users:', e)
  }

  if (users.length === 0) {
    return NextResponse.json({ message: 'No users to notify', sent: 0 })
  }

  // Split into active vs marketing
  const activeEmails: string[] = []
  const marketingEmails: string[] = []

  for (const user of users) {
    const hasAccess = (user.purchase_count > 0) || (user.packs_purchased > 0) || (!user.free_pack_used)
    if (hasAccess) {
      activeEmails.push(user.email)
    } else {
      marketingEmails.push(user.email)
    }
  }

  // Build batch payload
  const batch: any[] = []

  for (const email of activeEmails) {
    batch.push({
      from: FROM_EMAIL,
      to: [email],
      subject: '🏀 Your picks are ready!',
      html: activeUserEmail(gameCount),
    })
  }

  for (const email of marketingEmails) {
    batch.push({
      from: FROM_EMAIL,
      to: [email],
      subject: '🔥 Tonight\'s picks are in!',
      html: marketingEmail(),
    })
  }

  if (batch.length === 0) {
    return NextResponse.json({ message: 'No emails to send', sent: 0 })
  }

  // Send via Resend batch API (max 100 per batch on free tier)
  try {
    const res = await fetch('https://api.resend.com/emails/batch', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(batch.slice(0, 100)),
    })

    const result = await res.json()

    if (!res.ok) {
      console.error('Resend batch error:', result)
      return NextResponse.json({ error: 'Failed to send emails', details: result }, { status: 500 })
    }

    return NextResponse.json({
      message: 'Emails sent',
      sent: Math.min(batch.length, 100),
      active: activeEmails.length,
      marketing: marketingEmails.length,
    })
  } catch (e: any) {
    console.error('Resend API error:', e)
    return NextResponse.json({ error: 'Email send failed', details: e.message }, { status: 500 })
  }
}
