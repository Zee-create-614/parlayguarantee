'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'

interface TicketLeg {
  game_id: string
  team: string
  spread_at_purchase: string | number | null
  bet_type: string
  odds: string | number | null
  sport: string
  result: 'win' | 'loss' | 'push' | null
  covered: boolean | null
}

interface Ticket {
  id: string
  user_id: string
  purchase_time: string
  pack_type: string
  stripe_payment_intent_id: string
  legs: TicketLeg[]
  refund_eligible: boolean | null
  refund_status: 'pending' | 'approved' | 'denied'
  admin_override: boolean
  created_at: string
  scored_at: string | null
}

interface Stats {
  total: number
  pending: number
  approved: number
  denied: number
  eligible: number
  not_eligible: number
  unscored: number
}

const PACK_LABELS: Record<string, string> = {
  single: 'Single Pick ($5)',
  '2leg': '2-Leg Parlay ($10)',
  '3leg': '3-Leg Parlay ($20)',
  '4leg': '4-Leg Parlay ($35)',
  '5leg': '5-Leg Parlay ($50)',
  '6leg': '6-Leg Parlay ($75)',
  '7leg': '7-Leg Parlay ($100)',
}

export default function AdminRefundsPage() {
  const router = useRouter()
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pw, setPw] = useState('')

  // Filters
  const [filterPackType, setFilterPackType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterDateFrom, setFilterDateFrom] = useState('')
  const [filterDateTo, setFilterDateTo] = useState('')

  // Expanded ticket details
  const [expandedId, setExpandedId] = useState<string | null>(null)

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const urlPw = urlParams.get('pw')
    if (!urlPw || urlPw !== 'parlay2026') {
      router.push('/?error=unauthorized')
      return
    }
    setPw(urlPw)
  }, [router])

  const fetchData = useCallback(async () => {
    if (!pw) return
    try {
      const params = new URLSearchParams({ pw })
      if (filterPackType) params.set('pack_type', filterPackType)
      if (filterStatus) params.set('refund_status', filterStatus)
      if (filterDateFrom) params.set('date_from', filterDateFrom)
      if (filterDateTo) params.set('date_to', filterDateTo)

      const res = await fetch(`/api/admin/refunds?${params}`)
      if (!res.ok) throw new Error('Failed to fetch')
      const data = await res.json()
      setTickets(data.tickets || [])
      setStats(data.stats || null)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [pw, filterPackType, filterStatus, filterDateFrom, filterDateTo])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  const handleRefundAction = async (ticketId: string, status: 'approved' | 'denied', processStripe = false) => {
    try {
      const res = await fetch(`/api/admin/refunds/${ticketId}?pw=${pw}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pw, status, process_stripe: processStripe }),
      })
      if (!res.ok) throw new Error('Failed to update')
      await fetchData()
    } catch (err) {
      alert('Failed to update refund status')
    }
  }

  const handleScoreAll = async () => {
    try {
      const res = await fetch('/api/tickets/score', { method: 'POST' })
      const data = await res.json()
      alert(`Scored ${data.scored} tickets, skipped ${data.skipped}`)
      await fetchData()
    } catch {
      alert('Failed to score tickets')
    }
  }

  const formatDate = (d: string) => {
    if (!d) return 'N/A'
    return new Date(d).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-bg-primary via-bg-primary to-bg-secondary flex items-center justify-center">
        <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-accent-green"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-bg-primary via-bg-primary to-bg-secondary">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gradient">Refund Dashboard</h1>
            <p className="text-text-muted mt-1">Ticket management &amp; refund processing</p>
          </div>
          <button
            onClick={handleScoreAll}
            className="bg-accent-gold hover:bg-accent-gold/80 text-black font-bold py-2 px-4 rounded-lg"
          >
            ⚡ Score All Tickets
          </button>
        </div>

        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 mb-8">
            {[
              { label: 'Total', value: stats.total, color: 'text-white' },
              { label: 'Pending', value: stats.pending, color: 'text-yellow-400' },
              { label: 'Approved', value: stats.approved, color: 'text-green-400' },
              { label: 'Denied', value: stats.denied, color: 'text-red-400' },
              { label: 'Eligible', value: stats.eligible, color: 'text-green-300' },
              { label: 'Not Eligible', value: stats.not_eligible, color: 'text-red-300' },
              { label: 'Unscored', value: stats.unscored, color: 'text-gray-400' },
            ].map(s => (
              <div key={s.label} className="card text-center">
                <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
                <div className="text-text-muted text-xs mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        <div className="card mb-6">
          <div className="flex flex-wrap gap-4 items-end">
            <div>
              <label className="block text-text-muted text-xs mb-1">Pack Type</label>
              <select
                value={filterPackType}
                onChange={e => setFilterPackType(e.target.value)}
                className="bg-bg-primary border border-accent-green/20 rounded px-3 py-2 text-text-primary text-sm"
              >
                <option value="">All</option>
                {Object.entries(PACK_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-text-muted text-xs mb-1">Status</label>
              <select
                value={filterStatus}
                onChange={e => setFilterStatus(e.target.value)}
                className="bg-bg-primary border border-accent-green/20 rounded px-3 py-2 text-text-primary text-sm"
              >
                <option value="">All</option>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="denied">Denied</option>
              </select>
            </div>
            <div>
              <label className="block text-text-muted text-xs mb-1">From</label>
              <input
                type="date"
                value={filterDateFrom}
                onChange={e => setFilterDateFrom(e.target.value)}
                className="bg-bg-primary border border-accent-green/20 rounded px-3 py-2 text-text-primary text-sm"
              />
            </div>
            <div>
              <label className="block text-text-muted text-xs mb-1">To</label>
              <input
                type="date"
                value={filterDateTo}
                onChange={e => setFilterDateTo(e.target.value)}
                className="bg-bg-primary border border-accent-green/20 rounded px-3 py-2 text-text-primary text-sm"
              />
            </div>
            <button
              onClick={() => { setFilterPackType(''); setFilterStatus(''); setFilterDateFrom(''); setFilterDateTo('') }}
              className="text-accent-green hover:text-accent-green/80 text-sm underline pb-2"
            >
              Clear
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="card mb-6 border border-red-500/30 bg-red-500/10">
            <p className="text-red-400">{error}</p>
          </div>
        )}

        {/* Tickets Table */}
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-accent-green/20">
                <th className="text-left py-3 px-2 text-accent-green">ID</th>
                <th className="text-left py-3 px-2 text-accent-green">User</th>
                <th className="text-left py-3 px-2 text-accent-green">Pack</th>
                <th className="text-left py-3 px-2 text-accent-green">Purchased</th>
                <th className="text-left py-3 px-2 text-accent-green">Legs</th>
                <th className="text-left py-3 px-2 text-accent-green">Eligible</th>
                <th className="text-left py-3 px-2 text-accent-green">Status</th>
                <th className="text-left py-3 px-2 text-accent-green">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map(ticket => (
                <>
                  <tr
                    key={ticket.id}
                    className="border-b border-accent-green/10 hover:bg-bg-primary/30 cursor-pointer"
                    onClick={() => setExpandedId(expandedId === ticket.id ? null : ticket.id)}
                  >
                    <td className="py-3 px-2 font-mono text-text-muted">#{ticket.id}</td>
                    <td className="py-3 px-2 text-text-primary">{ticket.user_id}</td>
                    <td className="py-3 px-2">
                      <span className="px-2 py-1 rounded text-xs font-bold bg-accent-gold/20 text-accent-gold">
                        {PACK_LABELS[ticket.pack_type] || ticket.pack_type}
                      </span>
                    </td>
                    <td className="py-3 px-2 text-text-muted">{formatDate(ticket.purchase_time)}</td>
                    <td className="py-3 px-2">
                      <div className="flex gap-1">
                        {ticket.legs.map((leg, i) => (
                          <span
                            key={i}
                            className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                              leg.covered === true ? 'bg-green-500/30 text-green-400' :
                              leg.covered === false ? 'bg-red-500/30 text-red-400' :
                              'bg-gray-500/30 text-gray-400'
                            }`}
                            title={`${leg.team}: ${leg.covered === true ? 'Covered' : leg.covered === false ? 'Missed' : 'Pending'}`}
                          >
                            {leg.covered === true ? '✓' : leg.covered === false ? '✗' : '?'}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3 px-2">
                      <span className={`px-2 py-1 rounded text-xs font-bold ${
                        ticket.refund_eligible === true ? 'bg-green-500/20 text-green-400' :
                        ticket.refund_eligible === false ? 'bg-red-500/20 text-red-400' :
                        'bg-gray-500/20 text-gray-400'
                      }`}>
                        {ticket.refund_eligible === true ? 'Yes' :
                         ticket.refund_eligible === false ? 'No' : 'Pending'}
                      </span>
                    </td>
                    <td className="py-3 px-2">
                      <span className={`px-2 py-1 rounded text-xs font-bold ${
                        ticket.refund_status === 'approved' ? 'bg-green-500/20 text-green-400' :
                        ticket.refund_status === 'denied' ? 'bg-red-500/20 text-red-400' :
                        'bg-yellow-500/20 text-yellow-400'
                      }`}>
                        {ticket.refund_status.toUpperCase()}
                        {ticket.admin_override ? ' (manual)' : ''}
                      </span>
                    </td>
                    <td className="py-3 px-2" onClick={e => e.stopPropagation()}>
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleRefundAction(ticket.id, 'approved', true)}
                          className="px-2 py-1 rounded text-xs font-bold bg-green-600 hover:bg-green-500 text-white"
                          title="Approve & process Stripe refund"
                        >
                          ✓ Approve
                        </button>
                        <button
                          onClick={() => handleRefundAction(ticket.id, 'denied')}
                          className="px-2 py-1 rounded text-xs font-bold bg-red-600 hover:bg-red-500 text-white"
                        >
                          ✗ Deny
                        </button>
                      </div>
                    </td>
                  </tr>
                  {/* Expanded leg details */}
                  {expandedId === ticket.id && (
                    <tr key={`${ticket.id}-details`}>
                      <td colSpan={8} className="py-4 px-6 bg-bg-primary/50">
                        <div className="text-xs text-text-muted mb-2">
                          Stripe PI: <span className="font-mono">{ticket.stripe_payment_intent_id}</span>
                          {ticket.scored_at && <> · Scored: {formatDate(ticket.scored_at)}</>}
                        </div>
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-accent-green/10">
                              <th className="text-left py-2 px-2 text-accent-green">Team</th>
                              <th className="text-left py-2 px-2 text-accent-green">Sport</th>
                              <th className="text-left py-2 px-2 text-accent-green">Bet Type</th>
                              <th className="text-left py-2 px-2 text-accent-green">Spread/Odds at Purchase</th>
                              <th className="text-left py-2 px-2 text-accent-green">Result</th>
                              <th className="text-left py-2 px-2 text-accent-green">Covered</th>
                            </tr>
                          </thead>
                          <tbody>
                            {ticket.legs.map((leg, i) => (
                              <tr key={i} className={`border-b border-accent-green/5 ${
                                leg.covered === true ? 'bg-green-500/5' :
                                leg.covered === false ? 'bg-red-500/5' : ''
                              }`}>
                                <td className="py-2 px-2 font-medium text-text-primary">{leg.team}</td>
                                <td className="py-2 px-2 text-text-muted">{leg.sport || '—'}</td>
                                <td className="py-2 px-2 text-text-muted">{leg.bet_type}</td>
                                <td className="py-2 px-2 text-accent-gold font-mono">
                                  {leg.spread_at_purchase ?? leg.odds ?? '—'}
                                </td>
                                <td className="py-2 px-2 text-text-muted">{leg.result ?? 'Pending'}</td>
                                <td className="py-2 px-2">
                                  <span className={`font-bold ${
                                    leg.covered === true ? 'text-green-400' :
                                    leg.covered === false ? 'text-red-400' :
                                    'text-gray-400'
                                  }`}>
                                    {leg.covered === true ? '✓ Covered' :
                                     leg.covered === false ? '✗ Missed' : '— Pending'}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>

          {tickets.length === 0 && (
            <div className="text-center py-12 text-text-muted">
              No tickets found. Tickets are created when purchases are completed.
            </div>
          )}
        </div>

        <div className="text-center text-text-muted text-sm mt-6">
          Auto-refreshes every 30 seconds · Click a row to expand leg details
        </div>
      </div>
    </div>
  )
}
