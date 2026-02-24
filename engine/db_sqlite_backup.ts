import Database from 'better-sqlite3'
import path from 'path'
import crypto from 'crypto'

const DB_PATH = path.join(process.cwd(), 'engine', 'users.db')

let _db: Database.Database | null = null

function getDb(): Database.Database {
  if (!_db) {
    _db = new Database(DB_PATH)
    _db.pragma('journal_mode = WAL')
    _db.exec(`
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
    _db.exec(`
      CREATE TABLE IF NOT EXISTS signup_fingerprints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        device_fingerprint TEXT,
        ip_hash TEXT,
        flagged INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `)
    _db.exec(`
      CREATE TABLE IF NOT EXISTS referral_clicks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referral_code TEXT,
        ip_hash TEXT,
        user_agent TEXT,
        converted BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `)
    _db.exec(`
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
    _db.exec(`
      CREATE TABLE IF NOT EXISTS referral_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT,
        referral_code TEXT,
        email TEXT,
        metadata TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `)
  }
  return _db
}

function generateReferralCode(): string {
  return crypto.randomBytes(3).toString('hex').toUpperCase()
}

export function logReferralClick(referralCode: string, ipHash: string, userAgent: string) {
  const db = getDb()
  db.prepare('INSERT INTO referral_clicks (referral_code, ip_hash, user_agent) VALUES (?, ?, ?)').run(referralCode, ipHash, userAgent)
  logReferralEvent('click', referralCode, '', JSON.stringify({ ip_hash: ipHash }))
}

export function logReferralEvent(eventType: string, referralCode: string, email: string, metadata: string = '{}') {
  const db = getDb()
  db.prepare('INSERT INTO referral_events (event_type, referral_code, email, metadata) VALUES (?, ?, ?, ?)').run(eventType, referralCode, email, metadata)
}

export function getReferralAnalytics() {
  const db = getDb()

  const totalUsers = (db.prepare('SELECT COUNT(*) as count FROM users').get() as any).count
  const referredUsers = (db.prepare('SELECT COUNT(*) as count FROM users WHERE referred_by IS NOT NULL AND referred_by != ""').get() as any).count
  const totalClicks = (db.prepare('SELECT COUNT(*) as count FROM referral_clicks').get() as any).count

  // Top referrers
  const topReferrers = db.prepare(`
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
  `).all()

  // Daily signups (last 30 days)
  const dailySignups = db.prepare(`
    SELECT 
      date(created_at) as date,
      COUNT(*) as total,
      SUM(CASE WHEN referred_by IS NOT NULL AND referred_by != '' THEN 1 ELSE 0 END) as referred,
      COUNT(*) - SUM(CASE WHEN referred_by IS NOT NULL AND referred_by != '' THEN 1 ELSE 0 END) as organic
    FROM users
    WHERE created_at >= datetime('now', '-30 days')
    GROUP BY date(created_at)
    ORDER BY date DESC
  `).all()

  // Daily clicks
  const dailyClicks = db.prepare(`
    SELECT date(created_at) as date, COUNT(*) as clicks
    FROM referral_clicks
    WHERE created_at >= datetime('now', '-30 days')
    GROUP BY date(created_at)
    ORDER BY date DESC
  `).all()

  // Referral chains - users who were referred AND then referred others
  const chains = db.prepare(`
    SELECT 
      u.email,
      u.referred_by as referred_by_code,
      u.referral_code,
      (SELECT COUNT(*) FROM users WHERE referred_by = u.referral_code) as referred_count
    FROM users u
    WHERE u.referred_by IS NOT NULL AND u.referred_by != ''
      AND (SELECT COUNT(*) FROM users WHERE referred_by = u.referral_code) > 0
    ORDER BY referred_count DESC
  `).all()

  // Viral coefficient: avg referrals per referred user who also refers
  const viralCoeff = chains.length > 0
    ? (chains as any[]).reduce((sum: number, c: any) => sum + c.referred_count, 0) / referredUsers
    : 0

  // Recent events
  const recentEvents = db.prepare(`
    SELECT * FROM referral_events ORDER BY created_at DESC LIMIT 20
  `).all()

  return {
    summary: {
      totalUsers,
      referredUsers,
      referralConversionRate: totalClicks > 0 ? ((referredUsers / totalClicks) * 100).toFixed(1) : '0',
      totalClicks,
      clickToSignupRate: totalClicks > 0 ? ((referredUsers / totalClicks) * 100).toFixed(1) : '0',
    },
    topReferrers,
    dailySignups,
    dailyClicks,
    chains,
    viralCoefficient: viralCoeff.toFixed(3),
    recentEvents,
  }
}

// Anti-abuse functions
export function checkFingerprintAbuse(fingerprint: string, email: string): boolean {
  const db = getDb()
  // Check if this fingerprint is associated with another account that already used free pack
  const existing = db.prepare(`
    SELECT sf.email FROM signup_fingerprints sf
    JOIN users u ON sf.email = u.email
    WHERE sf.device_fingerprint = ? AND sf.email != ? AND u.free_pack_used = 1
    LIMIT 1
  `).get(fingerprint, email)
  return !!existing
}

export function checkIPRateLimit(ipHash: string): boolean {
  const db = getDb()
  const count = (db.prepare(`
    SELECT COUNT(DISTINCT email) as cnt FROM signup_fingerprints
    WHERE ip_hash = ? AND created_at >= datetime('now', '-24 hours')
  `).get(ipHash) as any)?.cnt || 0
  return count >= 2
}

export function logSignupFingerprint(email: string, fingerprint: string, ipHash: string, flagged: boolean) {
  const db = getDb()
  db.prepare('INSERT INTO signup_fingerprints (email, device_fingerprint, ip_hash, flagged) VALUES (?, ?, ?, ?)')
    .run(email, fingerprint, ipHash, flagged ? 1 : 0)
}

export function markFreePackUsed(email: string) {
  const db = getDb()
  db.prepare('UPDATE users SET free_pack_used = 1 WHERE email = ?').run(email)
}

export function getAbuseReport() {
  const db = getDb()
  
  const fingerprintClusters = db.prepare(`
    SELECT device_fingerprint, GROUP_CONCAT(DISTINCT email) as emails, COUNT(DISTINCT email) as count
    FROM signup_fingerprints
    WHERE device_fingerprint IS NOT NULL AND device_fingerprint != ''
    GROUP BY device_fingerprint
    HAVING count > 1
    ORDER BY count DESC
    LIMIT 50
  `).all()

  const ipClusters = db.prepare(`
    SELECT ip_hash, GROUP_CONCAT(DISTINCT email) as emails, COUNT(DISTINCT email) as count
    FROM signup_fingerprints
    WHERE ip_hash IS NOT NULL AND ip_hash != ''
    GROUP BY ip_hash
    HAVING count > 1
    ORDER BY count DESC
    LIMIT 50
  `).all()

  const flaggedSignups = db.prepare(`
    SELECT * FROM signup_fingerprints WHERE flagged = 1 ORDER BY created_at DESC LIMIT 100
  `).all()

  const totalAbuse = (db.prepare('SELECT COUNT(*) as cnt FROM signup_fingerprints WHERE flagged = 1').get() as any)?.cnt || 0

  return { fingerprintClusters, ipClusters, flaggedSignups, totalAbuseAttempts: totalAbuse }
}

export function getOrCreateUser(email: string, referredBy?: string): any {
  const db = getDb()
  let user = db.prepare('SELECT * FROM users WHERE email = ?').get(email)
  if (!user) {
    const code = generateReferralCode()
    db.prepare(
      'INSERT INTO users (email, referral_code, referred_by) VALUES (?, ?, ?)'
    ).run(email, code, referredBy || null)
    // Credit referrer
    if (referredBy) {
      db.prepare('UPDATE users SET referral_credits = referral_credits + 1 WHERE referral_code = ?').run(referredBy)
      logReferralEvent('signup', referredBy, email, '{}')
      logReferralEvent('referral_credit_earned', referredBy, '', JSON.stringify({ referred_email: email }))
    }
    user = db.prepare('SELECT * FROM users WHERE email = ?').get(email)
  }
  return user
}

export function getUserByEmail(email: string): any {
  const db = getDb()
  return db.prepare('SELECT * FROM users WHERE email = ?').get(email)
}

export function getReferralCount(referralCode: string): number {
  const db = getDb()
  return ((db.prepare('SELECT COUNT(*) as cnt FROM users WHERE referred_by = ?').get(referralCode)) as any)?.cnt || 0
}

export function useReferralCredit(email: string): boolean {
  const db = getDb()
  const user = db.prepare('SELECT referral_credits FROM users WHERE email = ?').get(email) as any
  if (!user || user.referral_credits < 1) return false
  db.prepare('UPDATE users SET referral_credits = referral_credits - 1 WHERE email = ?').run(email)
  logReferralEvent('referral_credit_used', '', email, '{}')
  return true
}

export function useFreePackForUser(email: string) {
  const db = getDb()
  db.prepare("UPDATE users SET free_pack_used = 1, free_pack_date = datetime('now') WHERE email = ?").run(email)
  logReferralEvent('free_pack_used', '', email, '{}')
}

export function recordPurchase(purchase: {
  email: string
  tier: string
  sports: string
  payment_intent_id: string
  amount: number
  status: string
}) {
  const db = getDb()
  db.prepare(`
    INSERT OR IGNORE INTO purchases (email, tier, sports, payment_intent_id, amount, status)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(purchase.email, purchase.tier, purchase.sports, purchase.payment_intent_id, purchase.amount, purchase.status)
}

export function getPurchaseByPaymentIntent(paymentIntentId: string): any {
  const db = getDb()
  return db.prepare('SELECT * FROM purchases WHERE payment_intent_id = ?').get(paymentIntentId)
}

export function getUserPurchases(email: string): any[] {
  const db = getDb()
  return db.prepare('SELECT * FROM purchases WHERE email = ? ORDER BY created_at DESC').all(email) as any[]
}

export { getDb, generateReferralCode }
