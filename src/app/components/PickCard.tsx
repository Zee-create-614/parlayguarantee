'use client'

import { useState } from 'react'
import { Copy, CheckCircle2, Lock, ChevronDown, ChevronUp } from 'lucide-react'

interface GameData {
  home_team: string
  away_team: string
  game_date: string
  game_time: string
  predicted_winner: string
  confidence: number
  home_probability: number
  away_probability: number
  bet_type?: string
  bet_label?: string
}

interface PickData {
  pick_number: number
  type: 'parlay' | 'straight'
  legs?: number
  games: GameData[]
  combined_confidence?: number
  implied_payout?: string
  confidence?: number
  predicted_winner?: string
}

function confidenceColor(conf: number): string {
  if (conf >= 70) return 'text-accent-green'
  if (conf >= 60) return 'text-accent-gold'
  return 'text-loss-red'
}

function confidenceBarColor(conf: number): string {
  if (conf >= 70) return 'from-accent-green to-accent-green/70'
  if (conf >= 60) return 'from-accent-gold to-accent-gold/70'
  return 'from-loss-red to-loss-red/70'
}

export default function PickCard({
  pick,
  locked = false,
  productEmoji = '🎲',
}: {
  pick: PickData
  locked?: boolean
  productEmoji?: string
}) {
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const isParlay = pick.type === 'parlay'
  const games = pick.games || []
  const mainConfidence = isParlay
    ? pick.combined_confidence || 0
    : games[0]?.confidence || pick.confidence || 0

  const copyPick = () => {
    if (locked) return
    const lines = games.map(
      (g, i) =>
        `${isParlay ? `Leg ${i + 1}: ` : ''}${g.predicted_winner} (${(g.confidence || 0).toFixed(1)}%) — ${g.away_team} @ ${g.home_team}`
    )
    navigator.clipboard.writeText(lines.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (locked) {
    return (
      <div className="relative parlay-card opacity-60">
        <div className="absolute inset-0 bg-bg-secondary/80 backdrop-blur-sm flex items-center justify-center rounded-xl z-10">
          <div className="text-center">
            <Lock className="w-8 h-8 text-accent-gold mx-auto mb-2" />
            <div className="font-bold text-accent-gold">LOCKED</div>
            <div className="text-xs text-text-muted mt-1">
              Pick #{pick.pick_number} • {isParlay ? `${pick.legs}-Leg Parlay` : 'Straight'}
            </div>
          </div>
        </div>
        <div className="p-6">
          <div className="h-8 bg-bg-primary/30 rounded shimmer mb-3" />
          <div className="h-20 bg-bg-primary/30 rounded-lg shimmer mb-3" />
          <div className="h-6 bg-bg-primary/30 rounded shimmer w-1/2" />
        </div>
      </div>
    )
  }

  return (
    <div className="parlay-card">
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">{productEmoji}</span>
            <span className="text-xs font-bold text-accent-gold uppercase">
              {isParlay ? `${pick.legs}-Leg Parlay` : 'Straight Pick'}
            </span>
            <span className="text-xs bg-bg-primary/50 px-2 py-0.5 rounded-full text-text-muted">
              #{pick.pick_number}
            </span>
          </div>
          {isParlay && pick.implied_payout && (
            <div className="text-2xl font-bold text-accent-green">{pick.implied_payout} payout</div>
          )}
        </div>
        <button
          onClick={copyPick}
          className="p-2 bg-accent-green/20 hover:bg-accent-green/30 rounded-lg transition-colors"
          title="Copy pick"
        >
          {copied ? (
            <CheckCircle2 className="w-5 h-5 text-accent-green" />
          ) : (
            <Copy className="w-5 h-5 text-accent-green" />
          )}
        </button>
      </div>

      {/* Games / Legs */}
      <div className="space-y-3 mb-4">
        {games.slice(0, expanded ? undefined : 3).map((game, i) => (
          <div key={i} className="p-3 bg-bg-primary/50 rounded-lg">
            <div className="flex justify-between items-center mb-1">
              <div className="font-semibold text-sm flex items-center gap-1.5">
                {isParlay && <span className="text-text-muted mr-1">Leg {i + 1}:</span>}
                <span className="text-accent-green">{game.predicted_winner}</span>
                {game.bet_type === 'moneyline' || game.bet_label === 'ML' ? (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-gold/20 text-accent-gold font-bold">ML</span>
                ) : game.bet_label ? (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-green/20 text-accent-green font-bold">{game.bet_label}</span>
                ) : null}
              </div>
              <div className={`text-sm font-bold ${confidenceColor(game.confidence || 0)}`}>
                {(game.confidence || 0).toFixed(1)}%
              </div>
            </div>
            <div className="text-xs text-text-muted mb-2">
              {game.away_team} @ {game.home_team}
              {game.game_time && game.game_time !== '19:00' && ` • ${game.game_time} ET`}
            </div>
            {/* Confidence bar */}
            <div className="h-1 bg-bg-primary rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full bg-gradient-to-r ${confidenceBarColor(game.confidence || 0)} transition-all`}
                style={{ width: `${Math.min(game.confidence || 0, 100)}%` }}
              />
            </div>
          </div>
        ))}

        {games.length > 3 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-accent-gold hover:text-accent-gold/80 transition-colors mx-auto"
          >
            {expanded ? (
              <>Show less <ChevronUp className="w-3 h-3" /></>
            ) : (
              <>Show {games.length - 3} more legs <ChevronDown className="w-3 h-3" /></>
            )}
          </button>
        )}
      </div>

      {/* Footer stats */}
      <div className="flex items-center justify-between pt-3 border-t border-accent-green/10">
        <div className="text-xs text-text-muted">
          AI Confidence: <span className={`font-bold ${confidenceColor(mainConfidence)}`}>{mainConfidence.toFixed(1)}%</span>
        </div>
        {isParlay && (
          <div className="text-xs text-text-muted">
            {pick.legs} legs • {pick.implied_payout} multiplier
          </div>
        )}
      </div>
    </div>
  )
}
