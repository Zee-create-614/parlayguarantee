import { Redis } from '@upstash/redis'

// Initialize Redis client (uses UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN env vars)
let redis: Redis | null = null

function getRedis(): Redis {
  if (!redis) {
    const url = (process.env.UPSTASH_REDIS_REST_URL || '').trim()
    const token = (process.env.UPSTASH_REDIS_REST_TOKEN || '').trim()
    if (!url || !token) {
      throw new Error('Upstash Redis not configured')
    }
    redis = new Redis({ url, token })
  }
  return redis
}

// ─── User Types ───
export interface KVUser {
  email: string
  fullName: string
  phone: string
  address: any
  dob: string
  referralCode: string
  referredBy: string | null
  freePackUsed: boolean
  referralCredits: number
  createdAt: string
  lastLogin: string
  purchaseCount: number
}

// ─── User Operations ───

export async function getUser(email: string): Promise<KVUser | null> {
  try {
    const r = getRedis()
    return await r.get<KVUser>(`user:${email.toLowerCase()}`)
  } catch {
    return null
  }
}

export async function saveUser(user: KVUser): Promise<void> {
  try {
    const r = getRedis()
    const key = `user:${user.email.toLowerCase()}`
    await r.set(key, user)
    // Add to user index (sorted set by signup date)
    await r.zadd('users:all', { score: new Date(user.createdAt).getTime(), member: user.email.toLowerCase() })
  } catch (e) {
    console.error('KV saveUser error:', e)
  }
}

export async function createOrUpdateUser(data: {
  email: string
  fullName?: string
  phone?: string
  address?: any
  dob?: string
  referredBy?: string | null
}): Promise<{ user: KVUser; isNew: boolean }> {
  const r = getRedis()
  const email = data.email.toLowerCase()
  const existing = await getUser(email)

  if (existing) {
    // Update last login + any new profile data
    const updated: KVUser = {
      ...existing,
      lastLogin: new Date().toISOString(),
      fullName: data.fullName || existing.fullName,
      phone: data.phone || existing.phone,
      address: data.address || existing.address,
      dob: data.dob || existing.dob,
    }
    await saveUser(updated)
    return { user: updated, isNew: false }
  }

  // Generate referral code from email
  const crypto = require('crypto')
  const referralCode = crypto.createHash('md5').update(email).digest('hex').slice(0, 8).toUpperCase()

  const newUser: KVUser = {
    email,
    fullName: data.fullName || '',
    phone: data.phone || '',
    address: data.address || null,
    dob: data.dob || '',
    referralCode,
    referredBy: data.referredBy || null,
    freePackUsed: false,
    referralCredits: 0,
    createdAt: new Date().toISOString(),
    lastLogin: new Date().toISOString(),
    purchaseCount: 0,
  }

  await saveUser(newUser)

  // Track referral
  if (data.referredBy) {
    await r.sadd(`referrals:${data.referredBy}`, email)
  }

  // Add to recent signups list
  await r.lpush('users:recent', JSON.stringify({ email, name: newUser.fullName, at: newUser.createdAt }))
  await r.ltrim('users:recent', 0, 99) // Keep last 100

  return { user: newUser, isNew: true }
}

export async function markFreePackUsedKV(email: string): Promise<void> {
  const user = await getUser(email)
  if (user) {
    user.freePackUsed = true
    await saveUser(user)
  }
}

export async function incrementPurchaseCount(email: string): Promise<void> {
  const user = await getUser(email)
  if (user) {
    user.purchaseCount = (user.purchaseCount || 0) + 1
    await saveUser(user)
  }
}

// ─── Referral Operations ───

export async function getReferralCount(code: string): Promise<number> {
  try {
    const r = getRedis()
    return await r.scard(`referrals:${code}`) || 0
  } catch {
    return 0
  }
}

export async function addReferralCredit(referrerEmail: string): Promise<void> {
  const user = await getUser(referrerEmail)
  if (user) {
    user.referralCredits = (user.referralCredits || 0) + 1
    await saveUser(user)
  }
}

// ─── Free Signup Pick ───

export async function saveFreePick(email: string, pickData: any): Promise<void> {
  try {
    const r = getRedis()
    await r.set(`freepick:${email.toLowerCase()}`, {
      ...pickData,
      createdAt: new Date().toISOString(),
    })
  } catch (e) {
    console.error('KV saveFreePick error:', e)
  }
}

export async function getFreePick(email: string): Promise<any> {
  try {
    const r = getRedis()
    return await r.get(`freepick:${email.toLowerCase()}`)
  } catch {
    return null
  }
}

// ─── Admin / Stats ───

export async function getAllUsers(limit = 50): Promise<string[]> {
  try {
    const r = getRedis()
    return await r.zrange('users:all', 0, limit - 1, { rev: true }) as string[]
  } catch {
    return []
  }
}

export async function getRecentSignups(limit = 20): Promise<any[]> {
  try {
    const r = getRedis()
    const items = await r.lrange('users:recent', 0, limit - 1)
    return items.map((item: any) => typeof item === 'string' ? JSON.parse(item) : item)
  } catch {
    return []
  }
}

export async function getUserCount(): Promise<number> {
  try {
    const r = getRedis()
    return await r.zcard('users:all') || 0
  } catch {
    return 0
  }
}

// ─── Betting Config ───

export async function saveBettingConfig(email: string, config: any): Promise<void> {
  try {
    const r = getRedis()
    await r.set(`betting:${email.toLowerCase()}`, {
      ...config,
      updatedAt: new Date().toISOString(),
    })
  } catch (e) {
    console.error('KV saveBettingConfig error:', e)
  }
}

// ─── Instant Purchase Tracking (bypass Stripe search delay) ───
export async function recordPurchaseInstant(email: string, paymentIntentId: string, tier: string, pickIds: string[], parlayData: any): Promise<void> {
  const r = getRedis()
  const today = new Date().toISOString().split('T')[0]
  const key = `purchases:${email}:${today}`
  const purchase = { paymentIntentId, tier, pickIds, parlayData, createdAt: new Date().toISOString() }
  await r.rpush(key, JSON.stringify(purchase))
  await r.expire(key, 172800)
}

export async function getInstantPurchases(email: string): Promise<Array<{ paymentIntentId: string; tier: string; pickIds: string[]; parlayData: any; createdAt: string }>> {
  const r = getRedis()
  const today = new Date().toISOString().split('T')[0]
  const key = `purchases:${email}:${today}`
  const items = await r.lrange(key, 0, -1)
  return items.map((item: any) => typeof item === 'string' ? JSON.parse(item) : item)
}

export async function getInstantPickIds(email: string): Promise<string[]> {
  const purchases = await getInstantPurchases(email)
  return purchases.flatMap(p => p.pickIds || [])
}

export async function getBettingConfig(email: string): Promise<any> {
  try {
    const r = getRedis()
    return await r.get(`betting:${email.toLowerCase()}`)
  } catch {
    return null
  }
}
