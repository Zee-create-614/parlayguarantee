// Purchase Tracker — Uses Stripe as source of truth
// No local DB needed; queries Stripe for daily purchase limits and pick assignment

import Stripe from 'stripe'
import { TIER_CONFIGS, ML_TIER_CONFIGS } from './tier-config'

function getStripe() {
  return new Stripe((process.env.STRIPE_SECRET_KEY || '').trim(), {
    apiVersion: '2025-02-24.acacia',
  })
}

function todayDateString(): string {
  return new Date().toISOString().split('T')[0] // YYYY-MM-DD in UTC
}

function startOfTodayUnix(): number {
  const d = new Date()
  d.setUTCHours(0, 0, 0, 0)
  return Math.floor(d.getTime() / 1000)
}

export interface DailyPurchaseCount {
  [tierId: string]: number
}

/**
 * Get today's purchase counts for a user (by email) from Stripe.
 * Looks at successful PaymentIntents with our metadata.
 */
export async function getUserDailyPurchases(email: string): Promise<DailyPurchaseCount> {
  const stripe = getStripe()
  const counts: DailyPurchaseCount = {}

  // Search for today's payments by this email (includes both auto-capture and manual hold)
  const paymentIntents = await stripe.paymentIntents.search({
    query: `metadata["email"]:"${email}" AND metadata["type"]:"parlayguarantee_parlay" AND created>${startOfTodayUnix()}`,
    limit: 20,
  })

  for (const pi of paymentIntents.data) {
    if (pi.status !== 'succeeded' && pi.status !== 'requires_capture') continue
    const tier = pi.metadata.tier || ''
    counts[tier] = (counts[tier] || 0) + 1
  }

  return counts
}

/**
 * Check if user can purchase a given tier today.
 */
export async function canUserPurchase(email: string, tierId: string): Promise<{ allowed: boolean; reason?: string; currentCount: number; limit: number }> {
  const config = TIER_CONFIGS[tierId] || ML_TIER_CONFIGS[tierId]
  if (!config) {
    return { allowed: false, reason: 'Invalid tier', currentCount: 0, limit: 0 }
  }

  const counts = await getUserDailyPurchases(email)
  const currentCount = counts[tierId] || 0

  if (currentCount >= config.dailyLimit) {
    return {
      allowed: false,
      reason: `Daily limit reached (${config.dailyLimit}x ${config.name} per day)`,
      currentCount,
      limit: config.dailyLimit,
    }
  }

  return { allowed: true, currentCount, limit: config.dailyLimit }
}

/**
 * Get all pick IDs assigned to a user today (from Stripe metadata).
 * Used to enforce unique pick assignment.
 */
export async function getUserDailyPickIds(email: string): Promise<string[]> {
  const stripe = getStripe()
  const pickIds: string[] = []

  const paymentIntents = await stripe.paymentIntents.search({
    query: `metadata["email"]:"${email}" AND metadata["type"]:"parlayguarantee_parlay" AND created>${startOfTodayUnix()}`,
    limit: 20,
  })

  for (const pi of paymentIntents.data) {
    if (pi.status !== 'succeeded' && pi.status !== 'requires_capture') continue
    const ids = pi.metadata.pick_ids
    if (ids) {
      pickIds.push(...ids.split(',').filter(Boolean))
    }
  }

  return pickIds
}

/**
 * Get all daily purchase limits with current counts for a user.
 * Used by the UI to show availability.
 */
export async function getUserLimitsOverview(email: string): Promise<Array<{
  tierId: string
  name: string
  legs: number
  price: number
  dailyLimit: number
  purchased: number
  available: number
}>> {
  const counts = await getUserDailyPurchases(email)

  return [...Object.values(TIER_CONFIGS), ...Object.values(ML_TIER_CONFIGS)].map(config => ({
    tierId: config.id,
    name: config.name,
    legs: config.legs,
    price: config.price,
    dailyLimit: config.dailyLimit,
    purchased: counts[config.id] || 0,
    available: Math.max(0, config.dailyLimit - (counts[config.id] || 0)),
  }))
}
