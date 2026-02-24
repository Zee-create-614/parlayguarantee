'use client'

import { useState, useEffect, Suspense, useCallback } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js'
import Header from '../components/Header'
import { Shield, ArrowLeft, Lock, AlertTriangle } from 'lucide-react'
import { TIER_CONFIGS } from '../../lib/tier-config'

const stripePromise = loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!)

const SPORTS_OPTIONS = ['NBA', 'NCAAB', 'Mixed (NBA + NCAAB)']

interface SportsbookOption {
  id: string
  name: string
  logo?: string
}

function CheckoutForm({ tier, sports, sportsbook, clientSecret, paymentIntentId }: {
  tier: string
  sports: string
  sportsbook: string
  clientSecret: string
  paymentIntentId: string
}) {
  const stripe = useStripe()
  const elements = useElements()
  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState('')
  const [agreed, setAgreed] = useState(false)

  const config = TIER_CONFIGS[tier]
  if (!config) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!stripe || !elements || !agreed) return

    setProcessing(true)
    setError('')

    const { error: submitError } = await elements.submit()
    if (submitError) {
      setError(submitError.message || 'Payment failed')
      setProcessing(false)
      return
    }

    const { error: confirmError } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}/checkout/success?tier=${tier}&sports=${encodeURIComponent(sports)}&sportsbook=${encodeURIComponent(sportsbook)}&pi=${paymentIntentId}`,
      },
    })

    if (confirmError) {
      setError(confirmError.message || 'Payment failed')
      setProcessing(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Order Summary */}
      <div className="card p-6 border-accent-green/30">
        <h2 className="text-lg font-bold mb-4">Order Summary</h2>
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-text-muted">Product</span>
            <span className="font-semibold">{config.icon} {config.name}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-text-muted">{config.legs === 1 ? 'Pick' : 'Legs'}</span>
            <span className="font-semibold">{config.legs} {config.legs === 1 ? 'pick' : 'picks'}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-text-muted">Sport</span>
            <span className="font-semibold">{sports}</span>
          </div>
          {sportsbook && (
            <div className="flex justify-between items-center">
              <span className="text-text-muted">Sportsbook</span>
              <span className="font-semibold">{sportsbook}</span>
            </div>
          )}
          <div className="border-t border-white/10 pt-3 flex justify-between items-center">
            <span className="text-text-muted">Total</span>
            <span className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-accent-green to-accent-gold">
              ${config.price}
            </span>
          </div>
        </div>

        <div className="mt-4 bg-accent-green/10 border border-accent-green/30 rounded-lg p-3">
          <div className="flex items-center gap-2 text-accent-green text-sm font-semibold">
            <Shield className="w-4 h-4" />
            {config.guarantee}
          </div>
        </div>

        <p className="text-xs text-text-muted mt-3">
          Picks will be auto-assigned by our AI immediately after payment.
        </p>
      </div>

      {/* Stripe Payment Element */}
      <div className="card p-6">
        <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
          <Lock className="w-4 h-4 text-accent-green" />
          Payment Details
        </h2>
        <PaymentElement options={{ layout: 'tabs' }} />
      </div>

      {/* Terms */}
      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-1 w-4 h-4 accent-accent-green"
        />
        <span className="text-sm text-text-muted">
          I agree to the{' '}
          <Link href="/terms" className="text-accent-green underline" target="_blank">Terms of Service</Link> and{' '}
          <Link href="/privacy" className="text-accent-green underline" target="_blank">Privacy Policy</Link>. I understand
          I will be charged ${config.price} and receive a full refund within 24 hours if {config.legs === 1 ? 'my pick loses' : 'any leg of my parlay loses'}.
          This is an AI-generated sports analysis service for entertainment purposes only. 21+ and where legal.
        </span>
      </label>

      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={!stripe || processing || !agreed}
        className="w-full py-4 px-6 rounded-lg font-bold text-lg transition-all bg-gradient-to-r from-accent-green to-emerald-400 text-black hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {processing ? (
          <span className="flex items-center justify-center gap-2">
            <div className="w-5 h-5 border-2 border-black border-t-transparent rounded-full animate-spin" />
            Processing...
          </span>
        ) : (
          <>Pay ${config.price}</>
        )}
      </button>

      <div className="flex items-center justify-center gap-4 text-xs text-text-muted">
        <span className="flex items-center gap-1"><Lock className="w-3 h-3" /> Secured by Stripe</span>
        <span>•</span>
        <span>256-bit SSL encryption</span>
      </div>
    </form>
  )
}

function CheckoutInner() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [selectedSport, setSelectedSport] = useState(searchParams.get('sports') || '')
  const [selectedBook, setSelectedBook] = useState('')
  const [sportsbooks, setSportsbooks] = useState<SportsbookOption[]>([])
  const [clientSecret, setClientSecret] = useState('')
  const [paymentIntentId, setPaymentIntentId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [step, setStep] = useState<'auth-check' | 'sport-select' | 'book-select' | 'payment'>('auth-check')

  const tier = searchParams.get('tier') || '2leg'
  const config = TIER_CONFIGS[tier]

  // Auth gate
  useEffect(() => {
    async function checkAuth() {
      try {
        const res = await fetch('/api/auth/me')
        const data = await res.json()
        if (data.authenticated && data.email) {
          setEmail(data.email)
          // If sport already selected via URL, go straight to creating checkout
          if (selectedSport && SPORTS_OPTIONS.includes(selectedSport)) {
            setStep('sport-select') // Will auto-proceed
          } else {
            setStep('sport-select')
          }
        } else {
          const returnUrl = `/checkout?tier=${tier}&sports=${encodeURIComponent(selectedSport)}`
          router.push(`/auth/signin?redirect=${encodeURIComponent(returnUrl)}`)
        }
      } catch {
        router.push('/auth/signin')
      }
    }
    checkAuth()
  }, [tier, selectedSport, router])

  // Fetch sportsbooks when entering book-select step
  useEffect(() => {
    if (step === 'book-select' && sportsbooks.length === 0) {
      fetch('/api/sportsbooks')
        .then(r => r.json())
        .then(data => setSportsbooks(data.sportsbooks || []))
        .catch(() => {})
    }
  }, [step, sportsbooks.length])

  const createCheckout = useCallback(async () => {
    if (!selectedSport || !selectedBook) {
      setError('Please select a sport and sportsbook.')
      return
    }
    setLoading(true)
    setError('')

    try {
      const res = await fetch('/api/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tier,
          sports: [selectedSport],
          email,
          sportsbook: selectedBook,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      setClientSecret(data.clientSecret)
      setPaymentIntentId(data.paymentIntentId)
      setStep('payment')
    } catch (err: any) {
      setError(err.message || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }, [email, tier, selectedSport, selectedBook])

  if (!config) {
    return (
      <div className="min-h-screen bg-bg-primary">
        <Header />
        <div className="max-w-lg mx-auto px-4 py-12 text-center">
          <AlertTriangle className="w-12 h-12 text-yellow-400 mx-auto mb-4" />
          <h1 className="text-2xl font-bold mb-2">Invalid Tier</h1>
          <p className="text-text-muted mb-6">This tier doesn&apos;t exist.</p>
          <Link href="/pricing" className="btn-primary">View Available Tiers</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg-primary">
      <Header />
      <div className="max-w-lg mx-auto px-4 py-12">
        <Link href="/pricing" className="flex items-center gap-2 text-text-muted hover:text-text-primary mb-8 text-sm">
          <ArrowLeft className="w-4 h-4" /> Back to pricing
        </Link>

        <div className="text-center mb-8">
          <div className="text-4xl mb-3">{config.icon}</div>
          <h1 className="text-2xl font-bold mb-1">{config.name}</h1>
          <p className="text-text-muted">{config.legs} {config.legs === 1 ? 'pick' : 'legs'} • ${config.price}</p>
        </div>

        {step === 'auth-check' ? (
          <div className="text-center py-12">
            <div className="w-8 h-8 border-2 border-accent-green border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-text-muted">Checking account...</p>
          </div>
        ) : step === 'sport-select' && !clientSecret ? (
          <div className="space-y-6">
            {/* Sport Selection */}
            <div className="card p-6">
              <label className="block text-sm font-semibold mb-4">Step 1: Select Your Sport</label>
              <div className="grid grid-cols-1 gap-3">
                {SPORTS_OPTIONS.map((sport) => (
                  <button
                    key={sport}
                    onClick={() => setSelectedSport(sport)}
                    className={`flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-all border ${
                      selectedSport === sport
                        ? 'border-accent-green bg-accent-green/10 text-accent-green'
                        : 'border-white/10 bg-bg-secondary hover:border-white/20 text-text-primary'
                    }`}
                  >
                    <span className="text-xl">
                      {sport === 'NBA' ? '🏀' : sport === 'NCAAB' ? '🎓🏀' : '🏀🔀'}
                    </span>
                    <span className="font-medium">{sport}</span>
                  </button>
                ))}
              </div>
              <p className="text-xs text-text-muted mt-3">
                Your picks will be auto-assigned from {selectedSport || 'your selected sport'} games.
              </p>
            </div>

            {error && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                {error}
              </div>
            )}

            <button
              onClick={() => { if (selectedSport) setStep('book-select') }}
              disabled={!selectedSport}
              className="w-full py-4 px-6 rounded-lg font-bold text-lg bg-gradient-to-r from-accent-green to-emerald-400 text-black hover:opacity-90 disabled:opacity-50"
            >
              Continue — Select Sportsbook
            </button>
          </div>
        ) : step === 'book-select' && !clientSecret ? (
          <div className="space-y-6">
            {/* Sportsbook Selection */}
            <div className="card p-6">
              <label className="block text-sm font-semibold mb-4">Step 2: Select Your Sportsbook</label>
              <div className="grid grid-cols-2 gap-3">
                {sportsbooks.map((book) => (
                  <button
                    key={book.id}
                    onClick={() => setSelectedBook(book.name)}
                    className={`flex items-center gap-2 px-4 py-3 rounded-lg text-left transition-all border ${
                      selectedBook === book.name
                        ? 'border-accent-green bg-accent-green/10 text-accent-green'
                        : 'border-white/10 bg-bg-secondary hover:border-white/20 text-text-primary'
                    }`}
                  >
                    <span className="text-xl">{book.logo || '📱'}</span>
                    <span className="font-medium text-sm">{book.name}</span>
                  </button>
                ))}
              </div>
              <p className="text-xs text-text-muted mt-3">
                Which sportsbook will you place this bet on?
              </p>
            </div>

            {error && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                {error}
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => setStep('sport-select')}
                className="py-4 px-6 rounded-lg font-bold text-lg border border-white/20 text-text-muted hover:border-white/40"
              >
                Back
              </button>
              <button
                onClick={createCheckout}
                disabled={loading || !selectedBook}
                className="flex-1 py-4 px-6 rounded-lg font-bold text-lg bg-gradient-to-r from-accent-green to-emerald-400 text-black hover:opacity-90 disabled:opacity-50"
              >
                {loading ? 'Generating your picks...' : `Continue to Payment — $${config.price}`}
              </button>
            </div>
          </div>
        ) : clientSecret ? (
          <Elements
            stripe={stripePromise}
            options={{
              clientSecret,
              appearance: {
                theme: 'night',
                variables: {
                  colorPrimary: '#00ff88',
                  colorBackground: '#1a1a2e',
                  colorText: '#e0e0e0',
                  borderRadius: '8px',
                },
              },
            }}
          >
            <CheckoutForm
              tier={tier}
              sports={selectedSport}
              sportsbook={selectedBook}
              clientSecret={clientSecret}
              paymentIntentId={paymentIntentId}
            />
          </Elements>
        ) : null}
      </div>
    </div>
  )
}

export default function CheckoutPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-bg-primary flex items-center justify-center">
          <div className="text-white">Loading checkout...</div>
        </div>
      }
    >
      <CheckoutInner />
    </Suspense>
  )
}
