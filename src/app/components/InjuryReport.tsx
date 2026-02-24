'use client'

import { useState, useEffect } from 'react'
import { AlertTriangle, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'

interface Injury {
  player: string
  team: string
  status: string
  injury: string
  position: string
  source: string
}

interface InjuryData {
  injuries: Injury[]
  by_team: Record<string, Injury[]>
  last_updated: string
  source_count: number
  cached?: boolean
  stale?: boolean
}

const STATUS_COLORS: Record<string, string> = {
  Out: 'bg-red-500/20 text-red-400 border-red-500/30',
  Doubtful: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  Questionable: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  Probable: 'bg-green-500/20 text-green-400 border-green-500/30',
  'Day-To-Day': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  GTD: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
}

const STATUS_ICONS: Record<string, string> = {
  Out: '🔴',
  Doubtful: '🟠',
  Questionable: '🟡',
  Probable: '🟢',
  'Day-To-Day': '🟡',
  GTD: '🟠',
}

export default function InjuryReport({ teams }: { teams?: string[] }) {
  const [data, setData] = useState<InjuryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [expandedTeams, setExpandedTeams] = useState<Set<string>>(new Set())

  const fetchInjuries = async (force = false) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/injuries${force ? '?force=true' : ''}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchInjuries()
  }, [])

  const toggleTeam = (team: string) => {
    setExpandedTeams(prev => {
      const next = new Set(prev)
      if (next.has(team)) next.delete(team)
      else next.add(team)
      return next
    })
  }

  if (loading && !data) {
    return (
      <div className="bg-gray-900/50 border border-gray-700 rounded-xl p-6">
        <div className="flex items-center gap-2 text-gray-400">
          <RefreshCw className="w-4 h-4 animate-spin" />
          Loading injury reports...
        </div>
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="bg-gray-900/50 border border-red-700/50 rounded-xl p-6">
        <div className="flex items-center gap-2 text-red-400">
          <AlertTriangle className="w-4 h-4" />
          Failed to load injuries: {error}
        </div>
      </div>
    )
  }

  if (!data || !data.by_team) return null

  // Filter to specific teams if provided
  const teamEntries = Object.entries(data.by_team)
    .filter(([team]) => !teams || teams.some(t => team.toLowerCase().includes(t.toLowerCase())))
    .sort(([a], [b]) => a.localeCompare(b))

  const totalOut = data.injuries.filter(i => i.status === 'Out').length
  const totalQuestionable = data.injuries.filter(i => ['Questionable', 'GTD', 'Day-To-Day'].includes(i.status)).length

  const lastUpdated = data.last_updated
    ? new Date(data.last_updated).toLocaleString('en-US', {
        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
      })
    : 'Unknown'

  return (
    <div className="bg-gray-900/50 border border-gray-700 rounded-xl overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-yellow-400" />
          <span className="font-semibold text-white">NBA Injury Report</span>
          <span className="text-sm text-gray-400">
            🔴 {totalOut} Out · 🟡 {totalQuestionable} Questionable
          </span>
          {data.stale && (
            <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded">
              Stale
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">{lastUpdated}</span>
          <span
            role="button"
            onClick={(e) => { e.stopPropagation(); fetchInjuries(true) }}
            className="p-1 hover:bg-gray-700 rounded cursor-pointer"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
          </span>
          {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </div>
      </button>

      {/* Body */}
      {expanded && (
        <div className="border-t border-gray-700 divide-y divide-gray-800">
          {teamEntries.length === 0 ? (
            <div className="p-4 text-gray-400 text-sm">No injuries to display</div>
          ) : (
            teamEntries.map(([team, injuries]) => (
              <div key={team}>
                <button
                  onClick={() => toggleTeam(team)}
                  className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-gray-800/30"
                >
                  <span className="font-medium text-gray-200 text-sm">{team}</span>
                  <span className="text-xs text-gray-500">{injuries.length} player{injuries.length !== 1 ? 's' : ''}</span>
                </button>
                {expandedTeams.has(team) && (
                  <div className="px-4 pb-3 space-y-1.5">
                    {injuries.map((inj, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm">
                        <span>{STATUS_ICONS[inj.status] || '⚪'}</span>
                        <span className="text-gray-200 font-medium">{inj.player}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${STATUS_COLORS[inj.status] || 'bg-gray-700 text-gray-300 border-gray-600'}`}>
                          {inj.status}
                        </span>
                        {inj.injury && (
                          <span className="text-gray-500 text-xs">{inj.injury}</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
