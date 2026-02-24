import { createClient } from '@libsql/client'
import crypto from 'crypto'

// Turso database client
let _client: any = null

function getClient() {
  if (!_client) {
    const databaseUrl = process.env.TURSO_DATABASE_URL?.trim()
    const authToken = process.env.TURSO_AUTH_TOKEN?.trim()

    if (!databaseUrl || !authToken) {
      throw new Error('TURSO_DATABASE_URL and TURSO_AUTH_TOKEN environment variables are required')
    }

    _client = createClient({
      url: databaseUrl,
      authToken: authToken,
    })
  }
  return _client
}

// Initialize database with schema - async version
export async function initializeDatabase() {
  const client = getClient()
  
  // Create tables with proper async execution
  await client.execute(`
    CREATE TABLE IF NOT EXISTS users (
      email TEXT PRIMARY KEY,
      free_pack_used INTEGER DEFAULT 0,
      free_pack_date TEXT,
      referral_code TEXT UNIQUE,
      referred_by TEXT,
      referral_credits INTEGER DEFAULT 0,
      packs_purchased INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now'))
    )
  `)
  
  await client.execute(`
    CREATE TABLE IF NOT EXISTS signup_fingerprints (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT,
      device_fingerprint TEXT,
      ip_hash TEXT,
      flagged INTEGER DEFAULT 0,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `)
  
  await client.execute(`
    CREATE TABLE IF NOT EXISTS referral_clicks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      referral_code TEXT,
      ip_hash TEXT,
      user_agent TEXT,
      converted BOOLEAN DEFAULT 0,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `)
  
  await client.execute(`
    CREATE TABLE IF NOT EXISTS purchases (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL,
      tier TEXT NOT NULL,
      sports TEXT,
      payment_intent_id TEXT UNIQUE,
      amount INTEGER NOT NULL,
      status TEXT DEFAULT 'pending',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `)
  
  await client.execute(`
    CREATE TABLE IF NOT EXISTS referral_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_type TEXT,
      referral_code TEXT,
      email TEXT,
      metadata TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `)

  await client.execute(`
    CREATE TABLE IF NOT EXISTS daily_picks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      pick_date TEXT NOT NULL,
      sport TEXT NOT NULL,
      home TEXT NOT NULL,
      away TEXT NOT NULL,
      spread REAL,
      spread_str TEXT,
      pick TEXT NOT NULL,
      cover_prob REAL,
      enhanced_prob REAL,
      ml_pick TEXT,
      ml_prob REAL,
      total_line REAL,
      ou_pick TEXT,
      ou_prob REAL,
      upset_score REAL,
      upset_flip INTEGER DEFAULT 0,
      game_time TEXT,
      commence_time TEXT,
      book_count INTEGER,
      raw_json TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `)

  await client.execute(`
    CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_picks_date_teams ON daily_picks(pick_date, home, away)
  `)

  await client.execute(`
    CREATE TABLE IF NOT EXISTS tickets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_email TEXT NOT NULL,
      purchase_id INTEGER,
      pack_type TEXT NOT NULL,
      pick_date TEXT NOT NULL,
      legs_json TEXT NOT NULL,
      total_legs INTEGER NOT NULL,
      legs_won INTEGER DEFAULT 0,
      legs_lost INTEGER DEFAULT 0,
      legs_pushed INTEGER DEFAULT 0,
      legs_pending INTEGER,
      all_scored INTEGER DEFAULT 0,
      deposit_status TEXT DEFAULT 'held',
      scored_at DATETIME,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `)
}

function generateReferralCode(): string {
  return crypto.randomBytes(3).toString('hex').toUpperCase()
}

// All database operations are now async
export async function logReferralClick(referralCode: string, ipHash: string, userAgent: string) {
  const client = getClient()
  await client.execute({
    sql: 'INSERT INTO referral_clicks (referral_code, ip_hash, user_agent) VALUES (?, ?, ?)',
    args: [referralCode, ipHash, userAgent]
  })
  await logReferralEvent('click', referralCode, '', JSON.stringify({ ip_hash: ipHash }))
}

export async function logReferralEvent(eventType: string, referralCode: string, email: string, metadata: string = '{}') {
  const client = getClient()
  await client.execute({
    sql: 'INSERT INTO referral_events (event_type, referral_code, email, metadata) VALUES (?, ?, ?, ?)',
    args: [eventType, referralCode, email, metadata]
  })
}

export async function getReferralAnalytics() {
  const client = getClient()

  const totalUsersResult = await client.execute('SELECT COUNT(*) as count FROM users')
  const totalUsers = totalUsersResult.rows[0].count as number

  const referredUsersResult = await client.execute('SELECT COUNT(*) as count FROM users WHERE referred_by IS NOT NULL AND referred_by != ""')
  const referredUsers = referredUsersResult.rows[0].count as number

  const totalClicksResult = await client.execute('SELECT COUNT(*) as count FROM referral_clicks')
  const totalClicks = totalClicksResult.rows[0].count as number

  // Top referrers
  const topReferrersResult = await client.execute(`
    SELECT 
      u.email,
      u.referral_code,
      COUNT(r.email) as total_referred,
      SUM(CASE WHEN r.packs_purchased > 0 THEN 1 ELSE 0 END) as paid_conversions,
      SUM(CASE WHEN r.free_pack_used > 0 THEN 1 ELSE 0 END) as free_packs_used,
      (SELECT COUNT(*) FROM referral_clicks WHERE referral_code = u.referral_code) as clicks
    FROM users u
    LEFT JOIN users r ON r.referred_by = u.referral_code
    WHERE u.referral_code IS NOT NULL
    GROUP BY u.email, u.referral_code
    HAVING total_referred > 0
    ORDER BY total_referred DESC
    LIMIT 20
  `)

  // Daily signups (last 30 days)
  const dailySignupsResult = await client.execute(`
    SELECT 
      date(created_at) as date,
      COUNT(*) as total,
      SUM(CASE WHEN referred_by IS NOT NULL AND referred_by != '' THEN 1 ELSE 0 END) as referred,
      COUNT(*) - SUM(CASE WHEN referred_by IS NOT NULL AND referred_by != '' THEN 1 ELSE 0 END) as organic
    FROM users
    WHERE created_at >= datetime('now', '-30 days')
    GROUP BY date(created_at)
    ORDER BY date DESC
  `)

  // Daily clicks
  const dailyClicksResult = await client.execute(`
    SELECT date(created_at) as date, COUNT(*) as clicks
    FROM referral_clicks
    WHERE created_at >= datetime('now', '-30 days')
    GROUP BY date(created_at)
    ORDER BY date DESC
  `)

  // Referral chains - users who were referred AND then referred others
  const chainsResult = await client.execute(`
    SELECT 
      u.email,
      u.referred_by as referred_by_code,
      u.referral_code,
      (SELECT COUNT(*) FROM users WHERE referred_by = u.referral_code) as referred_count
    FROM users u
    WHERE u.referred_by IS NOT NULL AND u.referred_by != ''
      AND (SELECT COUNT(*) FROM users WHERE referred_by = u.referral_code) > 0
    ORDER BY referred_count DESC
  `)

  // Viral coefficient: avg referrals per referred user who also refers
  const viralCoeff = chainsResult.rows.length > 0
    ? (chainsResult.rows as any[]).reduce((sum: number, c: any) => sum + Number(c.referred_count), 0) / referredUsers
    : 0

  // Recent events
  const recentEventsResult = await client.execute(`
    SELECT * FROM referral_events ORDER BY created_at DESC LIMIT 20
  `)

  return {
    summary: {
      totalUsers,
      referredUsers,
      referralConversionRate: totalClicks > 0 ? ((referredUsers / totalClicks) * 100).toFixed(1) : '0',
      totalClicks,
      clickToSignupRate: totalClicks > 0 ? ((referredUsers / totalClicks) * 100).toFixed(1) : '0',
    },
    topReferrers: topReferrersResult.rows,
    dailySignups: dailySignupsResult.rows,
    dailyClicks: dailyClicksResult.rows,
    chains: chainsResult.rows,
    viralCoefficient: viralCoeff.toFixed(3),
    recentEvents: recentEventsResult.rows,
  }
}

// Anti-abuse functions - all async
export async function checkFingerprintAbuse(fingerprint: string, email: string): Promise<boolean> {
  const client = getClient()
  const result = await client.execute({
    sql: `
      SELECT sf.email FROM signup_fingerprints sf
      JOIN users u ON sf.email = u.email
      WHERE sf.device_fingerprint = ? AND sf.email != ? AND u.free_pack_used = 1
      LIMIT 1
    `,
    args: [fingerprint, email]
  })
  return result.rows.length > 0
}

export async function checkIPRateLimit(ipHash: string): Promise<boolean> {
  const client = getClient()
  const result = await client.execute({
    sql: `
      SELECT COUNT(DISTINCT email) as cnt FROM signup_fingerprints
      WHERE ip_hash = ? AND created_at >= datetime('now', '-24 hours')
    `,
    args: [ipHash]
  })
  const count = Number(result.rows[0]?.cnt) || 0
  return count >= 2
}

export async function logSignupFingerprint(email: string, fingerprint: string, ipHash: string, flagged: boolean) {
  const client = getClient()
  await client.execute({
    sql: 'INSERT INTO signup_fingerprints (email, device_fingerprint, ip_hash, flagged) VALUES (?, ?, ?, ?)',
    args: [email, fingerprint, ipHash, flagged ? 1 : 0]
  })
}

export async function markFreePackUsed(email: string) {
  const client = getClient()
  await client.execute({
    sql: 'UPDATE users SET free_pack_used = 1 WHERE email = ?',
    args: [email]
  })
}

export async function getAbuseReport() {
  const client = getClient()
  
  const fingerprintClustersResult = await client.execute(`
    SELECT device_fingerprint, GROUP_CONCAT(DISTINCT email) as emails, COUNT(DISTINCT email) as count
    FROM signup_fingerprints
    WHERE device_fingerprint IS NOT NULL AND device_fingerprint != ''
    GROUP BY device_fingerprint
    HAVING count > 1
    ORDER BY count DESC
    LIMIT 50
  `)

  const ipClustersResult = await client.execute(`
    SELECT ip_hash, GROUP_CONCAT(DISTINCT email) as emails, COUNT(DISTINCT email) as count
    FROM signup_fingerprints
    WHERE ip_hash IS NOT NULL AND ip_hash != ''
    GROUP BY ip_hash
    HAVING count > 1
    ORDER BY count DESC
    LIMIT 50
  `)

  const flaggedSignupsResult = await client.execute(`
    SELECT * FROM signup_fingerprints WHERE flagged = 1 ORDER BY created_at DESC LIMIT 100
  `)

  const totalAbuseResult = await client.execute('SELECT COUNT(*) as cnt FROM signup_fingerprints WHERE flagged = 1')
  const totalAbuse = Number(totalAbuseResult.rows[0]?.cnt) || 0

  return { 
    fingerprintClusters: fingerprintClustersResult.rows, 
    ipClusters: ipClustersResult.rows, 
    flaggedSignups: flaggedSignupsResult.rows, 
    totalAbuseAttempts: totalAbuse 
  }
}

export async function getOrCreateUser(email: string, referredBy?: string): Promise<any> {
  const client = getClient()
  
  let result = await client.execute({
    sql: 'SELECT * FROM users WHERE email = ?',
    args: [email]
  })
  
  let user = result.rows[0]
  if (!user) {
    const code = generateReferralCode()
    await client.execute({
      sql: 'INSERT INTO users (email, referral_code, referred_by) VALUES (?, ?, ?)',
      args: [email, code, referredBy || null]
    })
    
    // Credit referrer
    if (referredBy) {
      await client.execute({
        sql: 'UPDATE users SET referral_credits = referral_credits + 1 WHERE referral_code = ?',
        args: [referredBy]
      })
      await logReferralEvent('signup', referredBy, email, '{}')
      await logReferralEvent('referral_credit_earned', referredBy, '', JSON.stringify({ referred_email: email }))
    }
    
    result = await client.execute({
      sql: 'SELECT * FROM users WHERE email = ?',
      args: [email]
    })
    user = result.rows[0]
  }
  return user
}

export async function getUserByEmail(email: string): Promise<any> {
  const client = getClient()
  const result = await client.execute({
    sql: 'SELECT * FROM users WHERE email = ?',
    args: [email]
  })
  return result.rows[0] || null
}

export async function getReferralCount(referralCode: string): Promise<number> {
  const client = getClient()
  const result = await client.execute({
    sql: 'SELECT COUNT(*) as cnt FROM users WHERE referred_by = ?',
    args: [referralCode]
  })
  return Number(result.rows[0]?.cnt) || 0
}

export async function useReferralCredit(email: string): Promise<boolean> {
  const client = getClient()
  
  const userResult = await client.execute({
    sql: 'SELECT referral_credits FROM users WHERE email = ?',
    args: [email]
  })
  
  const user = userResult.rows[0]
  if (!user || Number(user.referral_credits) < 1) return false
  
  await client.execute({
    sql: 'UPDATE users SET referral_credits = referral_credits - 1 WHERE email = ?',
    args: [email]
  })
  await logReferralEvent('referral_credit_used', '', email, '{}')
  return true
}

export async function useFreePackForUser(email: string) {
  const client = getClient()
  await client.execute({
    sql: "UPDATE users SET free_pack_used = 1, free_pack_date = datetime('now') WHERE email = ?",
    args: [email]
  })
  await logReferralEvent('free_pack_used', '', email, '{}')
}

export async function recordPurchase(purchase: {
  email: string
  tier: string
  sports: string
  payment_intent_id: string
  amount: number
  status: string
}) {
  const client = getClient()
  await client.execute({
    sql: `
      INSERT OR IGNORE INTO purchases (email, tier, sports, payment_intent_id, amount, status)
      VALUES (?, ?, ?, ?, ?, ?)
    `,
    args: [purchase.email, purchase.tier, purchase.sports, purchase.payment_intent_id, purchase.amount, purchase.status]
  })
}

export async function getPurchaseByPaymentIntent(paymentIntentId: string): Promise<any> {
  const client = getClient()
  const result = await client.execute({
    sql: 'SELECT * FROM purchases WHERE payment_intent_id = ?',
    args: [paymentIntentId]
  })
  return result.rows[0] || null
}

export async function getUserPurchases(email: string): Promise<any[]> {
  const client = getClient()
  const result = await client.execute({
    sql: 'SELECT * FROM purchases WHERE email = ? ORDER BY created_at DESC',
    args: [email]
  })
  return result.rows as any[]
}

// Export the client getter and generator function
export { getClient, generateReferralCode }