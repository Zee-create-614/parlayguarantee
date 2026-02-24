'use client'

import { useState, useEffect } from 'react'

function maskEmail(email: string): string {
  const [local, domain] = email.split('@')
  if (!domain) return email
  return local[0] + '***@' + domain
}

interface Analytics {
  summary: {
    totalUsers: number
    referredUsers: number
    referralConversionRate: string
    totalClicks: number
    clickToSignupRate: string
  }
  topReferrers: Array<{
    email: string
    referral_code: string
    total_referred: number
    paid_conversions: number
    free_packs_used: number
    clicks: number
  }>
  dailySignups: Array<{
    date: string
    total: number
    referred: number
    organic: number
  }>
  dailyClicks: Array<{
    date: string
    clicks: number
  }>
  chains: Array<{
    email: string
    referred_by_code: string
    referral_code: string
    referred_count: number
  }>
  viralCoefficient: string
  recentEvents: Array<{
    id: number
    event_type: string
    referral_code: string
    email: string
    metadata: string
    created_at: string
  }>
}

export default function ReferralAdmin() {
  const [password, setPassword] = useState('')
  const [authenticated, setAuthenticated] = useState(false)
  const [data, setData] = useState<Analytics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchData = async (pw: string) => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`/api/admin/referrals?password=${encodeURIComponent(pw)}`)
      if (!res.ok) {
        if (res.status === 401) { setError('Wrong password'); setAuthenticated(false) }
        else setError('Failed to load')
        return
      }
      const json = await res.json()
      setData(json)
      setAuthenticated(true)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault()
    fetchData(password)
  }

  // Merge daily clicks into daily signups
  const mergedDaily = data ? data.dailySignups.map(d => {
    const clickDay = data.dailyClicks.find(c => c.date === d.date)
    return { ...d, clicks: clickDay?.clicks || 0 }
  }) : []

  if (!authenticated) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
        <form onSubmit={handleLogin} className="bg-gray-800 p-8 rounded-xl max-w-sm w-full">
          <h1 className="text-2xl font-bold text-white mb-6">🔐 Referral Analytics</h1>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Admin password"
            className="w-full p-3 rounded-lg bg-gray-700 text-white border border-gray-600 mb-4"
          />
          <button type="submit" className="w-full bg-green-600 hover:bg-green-500 text-white font-bold py-3 rounded-lg">
            {loading ? 'Loading...' : 'Access Dashboard'}
          </button>
          {error && <p className="text-red-400 mt-3 text-sm">{error}</p>}
        </form>
      </div>
    )
  }

  if (!data) return <div className="min-h-screen bg-gray-900 flex items-center justify-center text-white">Loading...</div>

  const maxBar = Math.max(...mergedDaily.map(d => d.total), 1)

  return (
    <div className="min-h-screen bg-gray-900 text-white p-4 md:p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">📊 Referral Analytics</h1>
          <button onClick={() => fetchData(password)} className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded-lg text-sm">
            ↻ Refresh
          </button>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          {[
            { label: 'Total Users', value: data.summary.totalUsers, icon: '👥' },
            { label: 'Referred Users', value: data.summary.referredUsers, icon: '🔗' },
            { label: 'Conversion Rate', value: data.summary.referralConversionRate + '%', icon: '📈' },
            { label: 'Link Clicks', value: data.summary.totalClicks, icon: '👆' },
            { label: 'Click→Signup', value: data.summary.clickToSignupRate + '%', icon: '🎯' },
          ].map(card => (
            <div key={card.label} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <div className="text-2xl mb-1">{card.icon}</div>
              <div className="text-2xl font-bold">{card.value}</div>
              <div className="text-gray-400 text-sm">{card.label}</div>
            </div>
          ))}
        </div>

        {/* Top Referrers */}
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 mb-8">
          <h2 className="text-xl font-bold mb-4">🏆 Top Referrers</h2>
          {data.topReferrers.length === 0 ? (
            <p className="text-gray-400">No referrals yet</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-700">
                    <th className="text-left py-2 pr-4">#</th>
                    <th className="text-left py-2 pr-4">Email</th>
                    <th className="text-left py-2 pr-4">Code</th>
                    <th className="text-right py-2 pr-4">Clicks</th>
                    <th className="text-right py-2 pr-4">Signups</th>
                    <th className="text-right py-2 pr-4">Paid</th>
                    <th className="text-right py-2">Free Packs</th>
                  </tr>
                </thead>
                <tbody>
                  {data.topReferrers.map((r, i) => (
                    <tr key={r.referral_code} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                      <td className="py-2 pr-4 font-bold text-yellow-400">{i + 1}</td>
                      <td className="py-2 pr-4 font-mono text-sm">{maskEmail(r.email)}</td>
                      <td className="py-2 pr-4 font-mono text-green-400">{r.referral_code}</td>
                      <td className="py-2 pr-4 text-right">{r.clicks}</td>
                      <td className="py-2 pr-4 text-right font-bold">{r.total_referred}</td>
                      <td className="py-2 pr-4 text-right text-green-400">{r.paid_conversions}</td>
                      <td className="py-2 text-right text-blue-400">{r.free_packs_used}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Daily Activity */}
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 mb-8">
          <h2 className="text-xl font-bold mb-4">📅 Daily Activity (Last 30 Days)</h2>
          {mergedDaily.length === 0 ? (
            <p className="text-gray-400">No data yet</p>
          ) : (
            <div className="space-y-1">
              <div className="flex text-xs text-gray-400 mb-2 px-1">
                <span className="w-24">Date</span>
                <span className="flex-1">Signups</span>
                <span className="w-16 text-right">Organic</span>
                <span className="w-16 text-right">Referred</span>
                <span className="w-16 text-right">Clicks</span>
              </div>
              {mergedDaily.map(d => (
                <div key={d.date} className="flex items-center text-sm px-1">
                  <span className="w-24 text-gray-300 font-mono text-xs">{d.date.slice(5)}</span>
                  <div className="flex-1 flex gap-0.5 h-5">
                    <div
                      className="bg-blue-500 rounded-sm"
                      style={{ width: `${(d.organic / maxBar) * 100}%` }}
                      title={`${d.organic} organic`}
                    />
                    <div
                      className="bg-green-500 rounded-sm"
                      style={{ width: `${(d.referred / maxBar) * 100}%` }}
                      title={`${d.referred} referred`}
                    />
                  </div>
                  <span className="w-16 text-right text-blue-400">{d.organic}</span>
                  <span className="w-16 text-right text-green-400">{d.referred}</span>
                  <span className="w-16 text-right text-gray-400">{d.clicks}</span>
                </div>
              ))}
              <div className="flex gap-4 text-xs text-gray-500 mt-3 px-1">
                <span><span className="inline-block w-3 h-3 bg-blue-500 rounded-sm mr-1" />Organic</span>
                <span><span className="inline-block w-3 h-3 bg-green-500 rounded-sm mr-1" />Referred</span>
              </div>
            </div>
          )}
        </div>

        <div className="grid md:grid-cols-2 gap-8 mb-8">
          {/* Referral Chains */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h2 className="text-xl font-bold mb-2">🔗 Referral Chains</h2>
            <p className="text-gray-400 text-sm mb-4">
              Viral Coefficient: <span className="text-green-400 font-bold">{data.viralCoefficient}</span>
            </p>
            {data.chains.length === 0 ? (
              <p className="text-gray-500 text-sm">No viral chains yet — referred users haven&apos;t referred others</p>
            ) : (
              <div className="space-y-2">
                {data.chains.map(c => (
                  <div key={c.email} className="bg-gray-700/50 rounded-lg p-3 text-sm">
                    <div className="font-mono text-xs text-gray-400">{maskEmail(c.email)}</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-yellow-400">← {c.referred_by_code}</span>
                      <span className="text-gray-500">→</span>
                      <span className="text-green-400">{c.referral_code}</span>
                      <span className="text-gray-500">→</span>
                      <span className="font-bold">{c.referred_count} users</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Activity */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h2 className="text-xl font-bold mb-4">⚡ Recent Activity</h2>
            {data.recentEvents.length === 0 ? (
              <p className="text-gray-400 text-sm">No events yet</p>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {data.recentEvents.map(e => (
                  <div key={e.id} className="flex items-start gap-3 text-sm border-b border-gray-700/50 pb-2">
                    <span className="text-lg">
                      {e.event_type === 'click' ? '👆' :
                       e.event_type === 'signup' ? '✅' :
                       e.event_type === 'paid' ? '💰' :
                       e.event_type === 'free_pack_used' ? '🎁' :
                       e.event_type === 'referral_credit_earned' ? '⭐' : '📋'}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium capitalize">{e.event_type.replace(/_/g, ' ')}</span>
                        {e.referral_code && <span className="text-green-400 font-mono text-xs">{e.referral_code}</span>}
                      </div>
                      {e.email && <div className="text-gray-400 text-xs font-mono">{maskEmail(e.email)}</div>}
                    </div>
                    <span className="text-gray-500 text-xs whitespace-nowrap">
                      {new Date(e.created_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
