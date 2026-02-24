'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Copy, Check, TrendingUp, TrendingDown, DollarSign, Users, ShoppingBag, Target, Settings, BarChart3, Gift, ArrowRight, Shield } from 'lucide-react'

interface PurchasedPick {
  id: string
  tier: string
  tierName: string
  type: 'purchase' | 'free_signup' | 'referral'
  sport: string
  price: number
  date: string
  status: 'pending' | 'won' | 'lost' | 'refunded'
  legs: Array<{
    team: string
    bet: string
    odds: number
    type: string
    sport: string
    result?: 'won' | 'lost' | 'pending'
  }>
  combinedOdds: string
  confidence: number
}

interface DFSLineup {
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

interface DashboardData {
  email: string
  referral: { code: string; count: number; credits: number }
  bettingConfig: { sportsbook: string; bet_amount_per_pick: number; tier: string; sports: string } | null
  purchases: PurchasedPick[]
  pickResults: { wins: number; losses: number; pushes: number; pending: number }
  roi: { totalSpent: number; totalRefunds: number; netCost: number }
  freeSignupPick: PurchasedPick | null
  dfsLineups: DFSLineup[]
}

export default function DashboardPage() {
  const router = useRouter()
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    fetch('/api/dashboard')
      .then(r => {
        if (!r.ok) { router.push('/auth/signin'); return null }
        return r.json()
      })
      .then(d => { if (d) setData(d); setLoading(false) })
      .catch(() => { router.push('/auth/signin') })
  }, [router])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-accent-green text-xl">Loading dashboard...</div>
      </div>
    )
  }

  if (!data) return null

  const winRate = data.pickResults.wins + data.pickResults.losses > 0
    ? ((data.pickResults.wins / (data.pickResults.wins + data.pickResults.losses)) * 100).toFixed(1)
    : '0.0'

  const referralLink = data.referral.code
    ? `https://parlayguarantee.com/?ref=${data.referral.code}`
    : ''

  const handleCopy = () => {
    navigator.clipboard.writeText(referralLink)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const statusBadge = (status: string) => {
    const styles: Record<string, string> = {
      pending: 'bg-accent-gold/20 text-accent-gold',
      won: 'bg-accent-green/20 text-accent-green',
      lost: 'bg-red-500/20 text-red-400',
      refunded: 'bg-blue-500/20 text-blue-400',
    }
    return styles[status] || styles.pending
  }

  return (
    <div className="min-h-screen bg-bg-primary">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gradient">Dashboard</h1>
            <p className="text-text-muted mt-1">{data.email}</p>
          </div>
          <Link href="/pricing" className="btn-primary py-2 px-6 flex items-center gap-2">
            <ShoppingBag className="w-4 h-4" /> Buy More Picks
          </Link>
        </div>

        {/* Free Signup Pick */}
        {data.freeSignupPick && (
          <div className="mb-6 relative overflow-hidden rounded-2xl border-2 border-accent-green/40 bg-gradient-to-r from-accent-green/10 via-accent-gold/5 to-accent-green/10">
            <div className="relative p-6">
              <div className="flex items-center gap-3 mb-4">
                <Gift className="w-7 h-7 text-accent-green" />
                <h2 className="text-2xl font-bold text-accent-green">🎁 Your Free Signup Pick</h2>
                <span className={`text-xs px-2 py-1 rounded-full ${statusBadge(data.freeSignupPick.status)}`}>
                  {data.freeSignupPick.status}
                </span>
              </div>
              <div className="space-y-2">
                {data.freeSignupPick.legs.map((leg, i) => (
                  <div key={i} className="flex items-center justify-between bg-bg-primary/50 rounded-lg px-4 py-3">
                    <div>
                      <span className="text-xs text-text-muted mr-2">Leg {i + 1}</span>
                      <span className="font-semibold">{leg.bet}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-text-muted">{leg.team}</span>
                      <span className={`text-sm font-bold ${leg.odds > 0 ? 'text-accent-green' : ''}`}>
                        {leg.odds > 0 ? '+' : ''}{leg.odds}
                      </span>
                      {leg.result && (
                        <span className={`text-xs px-2 py-0.5 rounded ${statusBadge(leg.result)}`}>
                          {leg.result}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {data.freeSignupPick.combinedOdds && (
                <div className="mt-3 flex items-center gap-4 text-sm">
                  <span className="text-text-muted">Combined: <span className="font-bold text-accent-green">{data.freeSignupPick.combinedOdds}</span></span>
                  <span className="text-text-muted">Confidence: <span className="font-bold text-accent-gold">{data.freeSignupPick.confidence > 1 ? data.freeSignupPick.confidence.toFixed(1) : (data.freeSignupPick.confidence * 100).toFixed(1)}%</span></span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Referral Banner */}
        <div className="mb-6 relative overflow-hidden rounded-2xl border-2 border-accent-gold/40 bg-gradient-to-r from-accent-gold/10 via-accent-green/5 to-accent-gold/10">
          <div className="relative p-6 md:p-8">
            <div className="flex flex-col md:flex-row md:items-center gap-6">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-3xl">🤝</span>
                  <h2 className="text-2xl md:text-3xl font-extrabold text-accent-gold">Refer a Friend</h2>
                </div>
                <p className="text-lg md:text-xl font-semibold text-white mb-1">
                  You <span className="text-accent-green">BOTH</span> get a <span className="text-accent-gold">FREE 3-Leg Parlay Pick</span>
                </p>
                <p className="text-text-muted text-sm md:text-base">
                  Your friend signs up with your link → you each get a free 3-leg parlay pick. No purchase required.
                </p>
                {data.referral.code && (
                  <div className="mt-4 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                    <input
                      readOnly
                      value={referralLink}
                      className="bg-bg-primary/60 border-2 border-accent-gold/30 rounded-xl px-4 py-3 text-sm sm:text-base flex-1 text-white font-mono tracking-wide focus:outline-none"
                    />
                    <button
                      onClick={handleCopy}
                      className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-bold text-bg-primary bg-accent-gold hover:bg-accent-gold/90 transition-all shadow-lg shadow-accent-gold/20"
                    >
                      {copied ? <><Check className="w-5 h-5" /> Copied!</> : <><Copy className="w-5 h-5" /> Copy Link</>}
                    </button>
                  </div>
                )}
              </div>
              <div className="flex flex-row md:flex-col gap-4 md:min-w-[140px]">
                <div className="flex-1 bg-bg-primary/40 backdrop-blur rounded-xl p-4 text-center border border-accent-gold/20">
                  <div className="text-3xl font-black text-accent-gold">{data.referral.count}</div>
                  <div className="text-xs text-text-muted font-medium uppercase tracking-wider mt-1">Friends Referred</div>
                </div>
                <div className="flex-1 bg-bg-primary/40 backdrop-blur rounded-xl p-4 text-center border border-accent-green/20">
                  <div className="text-3xl font-black text-accent-green">{data.referral.credits}</div>
                  <div className="text-xs text-text-muted font-medium uppercase tracking-wider mt-1">Free Picks Earned</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="card text-center">
            <Target className="w-5 h-5 mx-auto mb-1 text-accent-green" />
            <div className="text-2xl font-bold text-accent-green">{data.pickResults.wins}W - {data.pickResults.losses}L</div>
            <div className="text-xs text-text-muted">Record</div>
          </div>
          <div className="card text-center">
            <BarChart3 className="w-5 h-5 mx-auto mb-1 text-accent-gold" />
            <div className="text-2xl font-bold text-accent-gold">{winRate}%</div>
            <div className="text-xs text-text-muted">Win Rate</div>
          </div>
          <div className="card text-center">
            <DollarSign className="w-5 h-5 mx-auto mb-1 text-accent-green" />
            <div className="text-2xl font-bold">${data.roi.totalSpent.toFixed(2)}</div>
            <div className="text-xs text-text-muted">Total Spent</div>
          </div>
          <div className="card text-center">
            <Shield className="w-5 h-5 mx-auto mb-1 text-blue-400" />
            <div className="text-2xl font-bold text-blue-400">${data.roi.totalRefunds.toFixed(2)}</div>
            <div className="text-xs text-text-muted">Total Refunds</div>
          </div>
        </div>

        {/* Purchased Picks */}
        <div className="card mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Target className="w-5 h-5 text-accent-green" />
              <h2 className="text-xl font-bold">Your Picks</h2>
            </div>
            {data.pickResults.pending > 0 && (
              <span className="text-sm text-accent-gold">{data.pickResults.pending} pending</span>
            )}
          </div>
          {data.purchases.length > 0 ? (
            <div className="space-y-4">
              {data.purchases.map((pick, idx) => (
                <div key={idx} className="bg-bg-primary/50 rounded-xl p-4 border border-white/5">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold">{pick.tierName}</span>
                      {pick.type === 'free_signup' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-accent-green/20 text-accent-green">FREE</span>
                      )}
                      {pick.type === 'referral' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400">REFERRAL</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-text-muted">{pick.date}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadge(pick.status)}`}>
                        {pick.status}
                      </span>
                      {pick.price > 0 && (
                        <span className="text-xs text-text-muted">${pick.price}</span>
                      )}
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    {pick.legs.map((leg, i) => (
                      <div key={i} className="flex items-center justify-between text-sm bg-bg-secondary/30 rounded-lg px-3 py-2">
                        <div>
                          <span className="text-xs text-text-muted mr-2">{pick.legs.length > 1 ? `Leg ${i + 1}` : 'Pick'}</span>
                          <span className="font-semibold">{leg.bet}</span>
                          <span className="text-text-muted ml-2 text-xs">{leg.team}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-bold ${leg.odds > 0 ? 'text-accent-green' : ''}`}>
                            {leg.odds > 0 ? '+' : ''}{leg.odds}
                          </span>
                          {leg.result && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${statusBadge(leg.result)}`}>
                              {leg.result}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  {pick.combinedOdds && (
                    <div className="mt-2 text-xs text-text-muted">
                      Combined: <span className="font-bold text-accent-green">{pick.combinedOdds}</span>
                      {pick.confidence > 0 && <> • Confidence: <span className="font-bold text-accent-gold">{pick.confidence}%</span></>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <Target className="w-10 h-10 text-text-muted/30 mx-auto mb-2" />
              <p className="text-text-muted">No picks yet</p>
              <p className="text-text-muted text-sm mb-4">Purchase a pick or sign up to get your free 3-leg parlay</p>
              <Link href="/pricing" className="btn-primary inline-block py-2 px-6">
                Browse Tiers <ArrowRight className="w-4 h-4 inline ml-1" />
              </Link>
            </div>
          )}
        </div>

        {/* DFS Lineups Section */}
        {data.dfsLineups && data.dfsLineups.length > 0 && (
          <div className="card mb-6">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xl">🏀</span>
              <h2 className="text-xl font-bold">Free DraftKings Lineup</h2>
              <span className="text-xs px-2 py-1 rounded-full bg-accent-green/20 text-accent-green">
                Bonus — included with your purchase
              </span>
            </div>
            
            {data.dfsLineups.map((lineup, idx) => (
              <div key={idx} className="mb-6 last:mb-0">
                {data.dfsLineups.length > 1 && (
                  <h3 className="text-lg font-semibold mb-3 text-accent-gold">
                    Lineup {String.fromCharCode(65 + idx)} — {lineup.strategy}
                  </h3>
                )}
                
                <div className="bg-bg-primary/50 rounded-xl overflow-hidden">
                  <div className="px-4 py-3 bg-bg-secondary/30 border-b border-white/5">
                    <div className="flex justify-between items-center text-sm">
                      <span className="font-medium">Projected Points: <span className="text-accent-green font-bold">{lineup.projected_points}</span></span>
                      <span className="font-medium">Salary: <span className="text-accent-gold font-bold">${lineup.total_salary.toLocaleString()}</span> / ${lineup.salary_cap.toLocaleString()}</span>
                    </div>
                  </div>
                  
                  <div className="divide-y divide-white/5">
                    {lineup.players.map((player, playerIdx) => (
                      <div key={playerIdx} className="px-4 py-3 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 bg-accent-green/20 rounded-lg flex items-center justify-center">
                            <span className="text-xs font-bold text-accent-green">{player.position}</span>
                          </div>
                          <div>
                            <div className="font-semibold text-white">{player.name}</div>
                            <div className="text-xs text-text-muted">{player.team}</div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-bold text-accent-gold">${player.salary.toLocaleString()}</div>
                          <div className="text-xs text-text-muted">{player.projected.toFixed(1)} pts ({player.value.toFixed(1)}x)</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className="mt-3 text-xs text-text-muted bg-bg-primary/30 rounded-lg px-3 py-2">
                  <strong>How to use:</strong> Copy this lineup to DraftKings NBA contests. Players are selected based on {lineup.strategy.toLowerCase()} strategy for optimal performance.
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Buy More Picks CTA */}
        <div className="card bg-gradient-to-r from-accent-green/5 to-accent-gold/5 border-accent-green/20 text-center mb-6">
          <h3 className="text-xl font-bold mb-2">Want More Picks?</h3>
          <p className="text-text-muted text-sm mb-4">
            Choose from 7 tiers — $5 single picks to $100 7-leg parlays. Full refund guarantee on every purchase.
          </p>
          <Link href="/pricing" className="btn-primary inline-block py-3 px-8">
            Buy More Picks <ArrowRight className="w-4 h-4 inline ml-1" />
          </Link>
        </div>

        {/* Betting Config */}
        {data.bettingConfig && (
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <Settings className="w-5 h-5 text-accent-green" />
              <h2 className="text-xl font-bold">Betting Configuration</h2>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="bg-bg-primary/50 rounded-lg p-4">
                <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Sportsbook</div>
                <div className="font-bold text-lg">{data.bettingConfig.sportsbook}</div>
              </div>
              <div className="bg-bg-primary/50 rounded-lg p-4">
                <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Bet Amount Per Pick</div>
                <div className="font-bold text-lg text-accent-green">${data.bettingConfig.bet_amount_per_pick}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
