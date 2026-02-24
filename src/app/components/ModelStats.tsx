'use client'

import { Brain, Target, TrendingUp, Activity } from 'lucide-react'

interface ModelStatsProps {
  factorsAnalyzed?: number
  accuracy?: number
  gamesTracked?: number
  avgConfidence?: number
  generatedAt?: string | null
}

export default function ModelStats({
  factorsAnalyzed = 37,
  accuracy = 68.4,
  gamesTracked = 0,
  avgConfidence = 0,
  generatedAt,
}: ModelStatsProps) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-accent-green/30 bg-gradient-to-r from-bg-secondary via-bg-secondary/80 to-bg-secondary mb-8">
      {/* Top glow bar */}
      <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-accent-green via-accent-gold to-accent-green" />

      <div className="p-6">
        <div className="flex items-center gap-2 mb-4">
          <Brain className="w-5 h-5 text-accent-green" />
          <span className="text-sm font-bold uppercase tracking-wider text-accent-green">
            AI Prediction Engine
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Factors */}
          <div className="text-center p-4 bg-bg-primary/40 rounded-xl border border-accent-green/10">
            <Activity className="w-5 h-5 text-accent-gold mx-auto mb-2" />
            <div className="text-3xl font-bold text-accent-gold">{factorsAnalyzed}</div>
            <div className="text-xs text-text-muted mt-1">AI Factors Analyzed</div>
          </div>

          {/* Accuracy */}
          <div className="text-center p-4 bg-bg-primary/40 rounded-xl border border-accent-green/10">
            <Target className="w-5 h-5 text-accent-green mx-auto mb-2" />
            <div className="text-3xl font-bold text-accent-green">{accuracy}%</div>
            <div className="text-xs text-text-muted mt-1">Model Accuracy</div>
            {/* Confidence bar */}
            <div className="mt-2 h-1.5 bg-bg-primary rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-accent-green to-accent-gold transition-all"
                style={{ width: `${Math.min(accuracy, 100)}%` }}
              />
            </div>
          </div>

          {/* Games Tracked */}
          <div className="text-center p-4 bg-bg-primary/40 rounded-xl border border-accent-green/10">
            <TrendingUp className="w-5 h-5 text-accent-green mx-auto mb-2" />
            <div className="text-3xl font-bold text-white">{gamesTracked}</div>
            <div className="text-xs text-text-muted mt-1">Games Analyzed to Date</div>
          </div>

          {/* Avg Confidence */}
          <div className="text-center p-4 bg-bg-primary/40 rounded-xl border border-accent-green/10">
            <Brain className="w-5 h-5 text-accent-gold mx-auto mb-2" />
            <div className="text-3xl font-bold text-white">{avgConfidence > 0 ? `${avgConfidence}%` : '—'}</div>
            <div className="text-xs text-text-muted mt-1">Avg Confidence</div>
          </div>
        </div>

        {generatedAt && (
          <div className="mt-4 text-center text-xs text-text-muted">
            Last generated: {new Date(generatedAt).toLocaleString('en-US', { timeZone: 'America/New_York' })} ET
          </div>
        )}
      </div>
    </div>
  )
}
