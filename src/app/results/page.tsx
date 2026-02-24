'use client'

import Link from 'next/link'
import { Activity } from 'lucide-react'
import Header from '../components/Header'

export default function ResultsPage() {

  return (
    <div className="min-h-screen bg-bg-primary">
      <Header />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 pb-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl md:text-3xl font-bold mb-3">
            <span className="text-gradient">Live</span> Performance
          </h1>
          <p className="text-base text-text-muted mb-3">
            Real pick results tracked automatically — every win and loss
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-accent-green/10 border border-accent-green/30 rounded-full text-accent-green text-sm">
            <Activity className="w-4 h-4" />
            Live Results
          </div>
        </div>

        {/* Launch Message */}
        <div className="card text-center py-16 mb-8">
          <div className="text-5xl mb-4">🚀</div>
          <h2 className="text-2xl font-bold mb-3">Results Start Tonight</h2>
          <p className="text-text-muted max-w-lg mx-auto mb-6">
            Live performance tracking launches tonight. Every pick — wins and losses — will be displayed here with full transparency.
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-accent-green/10 border border-accent-green/30 rounded-full text-accent-green text-sm">
            <Activity className="w-4 h-4" />
            Check back after tonight&apos;s games
          </div>
        </div>

        {/* Transparency Statement */}
        <div className="card text-center">
          <h2 className="text-2xl font-bold mb-4">Our Commitment to Transparency</h2>
          <p className="text-text-muted mb-6 max-w-2xl mx-auto">
            Every pick result is publicly displayed here, including losses. We don&apos;t hide bad days — we learn from them and use that data to improve our AI model.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/pricing" className="btn-primary">
              View Tonight&apos;s Picks
            </Link>
            <Link href="/pricing" className="btn-secondary">
              See Pricing Plans
            </Link>
          </div>
        </div>

        {/* Legal Footer */}
        <div className="mt-12 p-6 bg-bg-secondary/30 rounded-lg border border-accent-green/20">
          <p className="text-sm text-text-muted text-center">
            <strong>Performance Disclaimer:</strong> Statistics shown reflect actual pick outcomes tracked by our system.
            Past performance does not guarantee future results.
            This is for entertainment and educational purposes only. 21+ only where legal.
          </p>
        </div>
      </div>
    </div>
  )
}
