// DFS Tier Mapping - Maps purchase tiers to DFS lineup strategies

export interface DFSLineup {
  platform: string
  strategy: string
  players: Array<{
    name: string
    team: string
    position: string
    salary: number
    projected: number
    value: number
  }>
  total_salary: number
  salary_cap: number
  projected_points: number
}

export interface DFSOutput {
  date: string
  generated_at: string
  lineups: {
    draftkings: DFSLineup[]
    fanduel: DFSLineup[]
  }
}

// Tier mapping based on requirements:
// - Single pick ($5) and 2-leg ($10) buyers → get "Balanced" lineup (good but not best)
// - 3-leg ($20) and 4-leg ($35) buyers → get "Max Projection" lineup
// - 5-leg+ ($50+) buyers → get "Max Projection" + "Usage Heavy" lineups (2 lineups)
export const DFS_TIER_MAPPING: Record<string, string[]> = {
  'free': ['Value Play'],          // Free signup bonus
  'single': ['Balanced'],
  '2leg': ['Balanced'], 
  '3leg': ['Max Projection'],
  '4leg': ['Max Projection'],
  '5leg': ['Max Projection', 'Usage Heavy'],
  '6leg': ['Max Projection', 'Usage Heavy'],
  '7leg': ['Max Projection', 'Usage Heavy'],
}

export function getDFSLineupsForTier(dfsData: DFSOutput | null, tier: string, platform: 'draftkings' | 'fanduel' = 'draftkings'): DFSLineup[] {
  if (!dfsData || !dfsData.lineups[platform]) {
    return []
  }

  const strategies = DFS_TIER_MAPPING[tier] || []
  const platformLineups = dfsData.lineups[platform]
  
  return strategies.map(strategy => 
    platformLineups.find(lineup => lineup.strategy === strategy)
  ).filter(Boolean) as DFSLineup[]
}

export function getDFSLineupsForPurchases(dfsData: DFSOutput | null, purchases: Array<{ tier: string; status: string }>, isSignedUp: boolean = true): DFSLineup[] {
  if (!dfsData) {
    return []
  }

  // Get the highest tier purchased (excluding refunded purchases)
  const validPurchases = purchases.filter(p => p.status !== 'refunded')
  if (validPurchases.length === 0) {
    // Free signup — give them the free tier DFS lineup
    if (isSignedUp) {
      return getDFSLineupsForTier(dfsData, 'free')
    }
    return []
  }

  // Tier hierarchy for determining highest tier
  const tierHierarchy = ['single', '2leg', '3leg', '4leg', '5leg', '6leg', '7leg']
  
  let highestTier = 'single'
  for (const purchase of validPurchases) {
    const currentTierIndex = tierHierarchy.indexOf(purchase.tier)
    const highestTierIndex = tierHierarchy.indexOf(highestTier)
    if (currentTierIndex > highestTierIndex) {
      highestTier = purchase.tier
    }
  }

  return getDFSLineupsForTier(dfsData, highestTier)
}