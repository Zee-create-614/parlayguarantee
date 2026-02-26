// Parlay Tier Configuration — Single source of truth

export interface TierConfig {
  id: string
  name: string
  legs: number
  price: number        // in dollars (0 = coming soon)
  priceInCents: number // for Stripe
  dailyLimit: number   // max purchases per account per day
  icon: string
  badge: string | null
  badgeColor: string
  description: string
  guarantee: string
}

export const TIER_CONFIGS: Record<string, TierConfig> = {
  'single': {
    id: 'single',
    name: 'Single Pick',
    legs: 1,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '🎯',
    badge: 'STARTER',
    badgeColor: 'accent-green',
    description: 'One AI-curated spread pick — auto-assigned from your sport.',
    guarantee: 'Loses? Full refund.',
  },
  '2leg': {
    id: '2leg',
    name: '2-Leg Parlay',
    legs: 2,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '🔥',
    badge: 'MOST POPULAR',
    badgeColor: 'accent-green',
    description: 'Two correlated picks with our highest-edge matchups.',
    guarantee: 'Any leg loses? Full refund.',
  },
  '3leg': {
    id: '3leg',
    name: '3-Leg Parlay',
    legs: 3,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '🏆',
    badge: 'BEST VALUE',
    badgeColor: 'accent-gold',
    description: 'Three-pick combo with exclusive mid-tier selections.',
    guarantee: 'Any leg loses? Full refund.',
  },
  '4leg': {
    id: '4leg',
    name: '4-Leg Parlay',
    legs: 4,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '💎',
    badge: null,
    badgeColor: 'accent-green',
    description: 'Four-pick parlay with premium AI-curated legs.',
    guarantee: 'Any leg loses? Full refund.',
  },
  '5leg': {
    id: '5leg',
    name: '5-Leg Parlay',
    legs: 5,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '⚡',
    badge: 'PREMIUM',
    badgeColor: 'accent-gold',
    description: 'Five exclusive picks — our highest-correlation edge combos.',
    guarantee: 'Any leg loses? Full refund.',
  },
  '6leg': {
    id: '6leg',
    name: '6-Leg Parlay',
    legs: 6,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '🚀',
    badge: 'ELITE',
    badgeColor: 'accent-gold',
    description: 'Six-leg mega parlay — reserved for max-payout hunters.',
    guarantee: 'Any leg loses? Full refund.',
  },
  '7leg': {
    id: '7leg',
    name: '7-Leg Parlay',
    legs: 7,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '👑',
    badge: 'ULTIMATE',
    badgeColor: 'purple-400',
    description: 'Seven-leg ultimate combo — our best curated parlay for maximum payout.',
    guarantee: 'Any leg loses? Full refund.',
  },
}

export const TIER_ORDER = ['single', '2leg', '3leg', '4leg', '5leg', '6leg', '7leg']

// ML-specific tiers
export const ML_TIER_CONFIGS: Record<string, TierConfig> = {
  'ml-single': {
    id: 'ml-single',
    name: 'ML Single Pick',
    legs: 1,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '🎯',
    badge: null,
    badgeColor: 'accent-green',
    description: 'One AI-curated moneyline pick — team to win outright.',
    guarantee: 'Loses? Full refund.',
  },
  'ml-2leg': {
    id: 'ml-2leg',
    name: 'ML 2-Leg Parlay',
    legs: 2,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '🔥',
    badge: 'NEW',
    badgeColor: 'accent-green',
    description: 'Two moneyline picks — both teams must win outright.',
    guarantee: 'Any leg loses? Full refund.',
  },
  'ml-3leg': {
    id: 'ml-3leg',
    name: 'ML 3-Leg Parlay',
    legs: 3,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '🏆',
    badge: null,
    badgeColor: 'accent-gold',
    description: 'Three moneyline picks — all teams must win outright.',
    guarantee: 'Any leg loses? Full refund.',
  },
  'ml-4leg': {
    id: 'ml-4leg',
    name: 'ML 4-Leg Parlay',
    legs: 4,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '💎',
    badge: null,
    badgeColor: 'accent-green',
    description: 'Four moneyline picks — premium ML combo for big payouts.',
    guarantee: 'Any leg loses? Full refund.',
  },
  'ml-5leg': {
    id: 'ml-5leg',
    name: 'ML 5-Leg Parlay',
    legs: 5,
    price: 0,
    priceInCents: 0,
    dailyLimit: 999,
    icon: '⚡',
    badge: null,
    badgeColor: 'accent-gold',
    description: 'Five moneyline picks — our highest-edge ML parlay.',
    guarantee: 'Any leg loses? Full refund.',
  },
}

export const ML_TIER_ORDER = ['ml-single', 'ml-2leg', 'ml-3leg', 'ml-4leg', 'ml-5leg']

export function getTierConfig(tierId: string): TierConfig | null {
  return TIER_CONFIGS[tierId] || ML_TIER_CONFIGS[tierId] || null
}
