'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import Header from '../../components/Header'
import { CheckCircle, ArrowRight } from 'lucide-react'
import { TIER_CONFIGS } from '../../../lib/tier-config'

function SuccessInner() {
  const searchParams = useSearchParams()
  const tier = searchParams.get('tier') || '2leg'
  const sports = searchParams.get('sports') || ''
  const sportsbook = searchParams.get('sportsbook') || ''
  const pi = searchParams.get('pi') || ''
  const [saved, setSaved] = useState(false)

  const config = TIER_CONFIGS[tier]

  // Record the purchase
  useEffect(() => {
    if (!pi) return
    fetch('/api/checkout/record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paymentIntentId: pi, tier, sports, sportsbook }),
    }).then(() => setSaved(true)).catch(() => setSaved(true))
  }, [pi, tier, sports, sportsbook])

  return (
    <div className="min-h-screen bg-bg-primary">
      <Header />
      <div className="max-w-lg mx-auto px-4 py-20 text-center">
        <div className="w-20 h-20 bg-accent-green rounded-full flex items-center justify-center mx-auto mb-6">
          <CheckCircle className="w-10 h-10 text-black" />
        </div>
        <h1 className="text-3xl font-bold mb-3">Payment Successful! {config?.icon || '🎯'}</h1>
        <p className="text-text-muted mb-2">
          Your {config?.name || 'picks'} have been auto-assigned to your account.
        </p>
        <p className="text-sm text-text-muted mb-2">
          Sport: <strong>{sports}</strong>
          {sportsbook && <> • Sportsbook: <strong>{sportsbook}</strong></>}
        </p>
        <p className="text-sm text-accent-green font-semibold mb-8">
          View your picks in the dashboard below.
        </p>

        <Link
          href="/dashboard"
          className="btn-primary text-lg py-4 px-8 inline-flex items-center gap-2"
        >
          View My Picks <ArrowRight className="w-5 h-5" />
        </Link>

        <p className="text-sm text-text-muted mt-6">
          Remember: if {config?.legs === 1 ? 'your pick loses' : 'any leg loses'}, you get a full ${config?.price || ''} refund within 24 hours.
        </p>
      </div>
    </div>
  )
}

export default function SuccessPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-bg-primary flex items-center justify-center"><div className="text-white">Loading...</div></div>}>
      <SuccessInner />
    </Suspense>
  )
}
