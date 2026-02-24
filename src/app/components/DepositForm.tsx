'use client'

import { useState } from 'react'
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from '@stripe/react-stripe-js'
import { loadStripe } from '@stripe/stripe-js'
import { Shield, Loader2, CheckCircle, XCircle } from 'lucide-react'

const stripePromise = loadStripe(
  process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!
)

function CheckoutForm({ onSuccess }: { onSuccess: (paymentIntentId: string) => void }) {
  const stripe = useStripe()
  const elements = useElements()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!stripe || !elements) return

    setLoading(true)
    setError(null)

    const { error: submitError } = await elements.submit()
    if (submitError) {
      setError(submitError.message || 'Validation failed')
      setLoading(false)
      return
    }

    const { error: confirmError, paymentIntent } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}/pricing?deposit=success`,
      },
      redirect: 'if_required',
    })

    if (confirmError) {
      setError(confirmError.message || 'Payment failed')
      setLoading(false)
      return
    }

    if (paymentIntent && paymentIntent.status === 'requires_capture') {
      onSuccess(paymentIntent.id)
    }

    setLoading(false)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <PaymentElement
        options={{
          layout: 'tabs',
        }}
      />

      {error && (
        <div className="flex items-center gap-2 text-red-400 text-sm bg-red-400/10 p-3 rounded-lg">
          <XCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={!stripe || loading}
        className="btn-primary w-full py-4 text-lg flex items-center justify-center gap-2 disabled:opacity-50"
      >
        {loading ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Processing...
          </>
        ) : (
          <>
            <Shield className="w-5 h-5" />
            Place $50 Deposit Hold
          </>
        )}
      </button>

      <p className="text-xs text-text-muted text-center">
        This places a $50 hold on your card. You are only charged if our accuracy threshold is met.
        If the threshold isn&apos;t met, the hold is released automatically — full refund.
      </p>
    </form>
  )
}

export default function DepositForm() {
  const [clientSecret, setClientSecret] = useState<string | null>(null)
  const [paymentIntentId, setPaymentIntentId] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'form' | 'success' | 'error'>('idle')
  const [email, setEmail] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  const startDeposit = async () => {
    setStatus('loading')
    setErrorMsg('')
    try {
      const res = await fetch('/api/create-payment-intent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      const data = await res.json()
      if (data.error) {
        setErrorMsg(data.error)
        setStatus('error')
        return
      }
      setClientSecret(data.clientSecret)
      setPaymentIntentId(data.paymentIntentId)
      setStatus('form')
    } catch {
      setErrorMsg('Failed to initialize payment. Please try again.')
      setStatus('error')
    }
  }

  const handleSuccess = (piId: string) => {
    setPaymentIntentId(piId)
    setStatus('success')
    // Store in localStorage so picks page can reference it
    localStorage.setItem('pg_payment_intent_id', piId)
    localStorage.setItem('pg_deposit_date', new Date().toISOString())
  }

  if (status === 'success') {
    return (
      <div className="text-center space-y-4 p-8">
        <CheckCircle className="w-16 h-16 text-accent-green mx-auto" />
        <h3 className="text-2xl font-bold">Deposit Hold Placed!</h3>
        <p className="text-text-muted">
          Your $50 hold is active. You now have access to tonight&apos;s full pick slate.
        </p>
        <p className="text-sm text-text-muted">
          If the accuracy threshold isn&apos;t met, the hold will be released automatically by tomorrow.
        </p>
        <a href="/picks" className="btn-primary inline-block mt-4 py-3 px-8">
          View Your Picks →
        </a>
      </div>
    )
  }

  if (status === 'form' && clientSecret) {
    return (
      <div className="max-w-md mx-auto">
        <Elements
          stripe={stripePromise}
          options={{
            clientSecret,
            appearance: {
              theme: 'night',
              variables: {
                colorPrimary: '#00ff88',
                colorBackground: '#1a1a2e',
                colorText: '#ffffff',
                colorDanger: '#ff4444',
                borderRadius: '8px',
              },
            },
          }}
        >
          <CheckoutForm onSuccess={handleSuccess} />
        </Elements>
      </div>
    )
  }

  return (
    <div className="max-w-md mx-auto space-y-4">
      <div>
        <label className="block text-sm text-text-muted mb-1">Email (for receipt)</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="your@email.com"
          className="w-full px-4 py-3 bg-bg-secondary border border-accent-green/30 rounded-lg text-white placeholder-text-muted focus:outline-none focus:border-accent-green"
        />
      </div>

      {errorMsg && (
        <div className="flex items-center gap-2 text-red-400 text-sm bg-red-400/10 p-3 rounded-lg">
          <XCircle className="w-4 h-4 flex-shrink-0" />
          {errorMsg}
        </div>
      )}

      <button
        onClick={startDeposit}
        disabled={status === 'loading'}
        className="btn-primary w-full py-4 text-lg flex items-center justify-center gap-2 disabled:opacity-50"
      >
        {status === 'loading' ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Setting up...
          </>
        ) : (
          <>
            <Shield className="w-5 h-5" />
            Place $50 Deposit & Get Picks
          </>
        )}
      </button>

      <p className="text-xs text-text-muted text-center">
        🔒 Secured by Stripe. Your card is never stored on our servers.
      </p>
    </div>
  )
}
