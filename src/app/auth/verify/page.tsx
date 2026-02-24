'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import Link from 'next/link'

function VerifyInner() {
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [user, setUser] = useState<any>(null)
  const searchParams = useSearchParams()
  const router = useRouter()

  useEffect(() => {
    const token = searchParams.get('token')
    
    if (!token) {
      setStatus('error')
      setMessage('No verification token provided')
      return
    }

    const ref = typeof window !== 'undefined' ? sessionStorage.getItem('parlayguarantee_ref') : null
    const refParam = ref ? `&ref=${encodeURIComponent(ref)}` : ''
    fetch(`/api/auth/verify-magic?token=${encodeURIComponent(token)}${refParam}`)
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          setStatus('success')
          setMessage(data.message)
          setUser(data.user)
          const redirect = searchParams.get('redirect') || '/dashboard'
          setTimeout(() => { router.push(redirect) }, 1500)
        } else {
          setStatus('error')
          setMessage(data.error || 'Verification failed')
        }
      })
      .catch(error => {
        console.error('Verification error:', error)
        setStatus('error')
        setMessage('Something went wrong during verification')
      })
  }, [searchParams, router])

  return (
    <div className="card text-center">
      {status === 'loading' && (
        <>
          <div className="w-16 h-16 bg-accent-green rounded-full flex items-center justify-center mx-auto mb-6">
            <Loader2 className="w-8 h-8 text-black animate-spin" />
          </div>
          <h1 className="text-2xl font-bold mb-4">Verifying your sign-in...</h1>
          <p className="text-text-muted">Please wait while we authenticate your magic link.</p>
        </>
      )}
      {status === 'success' && (
        <>
          <div className="w-16 h-16 bg-accent-green rounded-full flex items-center justify-center mx-auto mb-6">
            <CheckCircle className="w-8 h-8 text-black" />
          </div>
          <h1 className="text-2xl font-bold mb-4 text-accent-green">Welcome back!</h1>
          <p className="text-text-muted mb-4">{message}</p>
          {user && <p className="text-sm text-accent-gold mb-6">Signed in as: {user.email}</p>}
          <p className="text-sm text-text-muted">Redirecting you to tonight&apos;s picks...</p>
        </>
      )}
      {status === 'error' && (
        <>
          <div className="w-16 h-16 bg-loss-red rounded-full flex items-center justify-center mx-auto mb-6">
            <AlertCircle className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold mb-4 text-loss-red">Verification Failed</h1>
          <p className="text-text-muted mb-6">{message}</p>
          <div className="space-y-3">
            <Link href="/auth/signin" className="btn-primary w-full">Try Again</Link>
            <Link href="/" className="btn-secondary w-full">Back to Home</Link>
          </div>
        </>
      )}
    </div>
  )
}

export default function VerifyPage() {
  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        <Suspense fallback={<div className="text-white text-center">Verifying...</div>}>
          <VerifyInner />
        </Suspense>
        <div className="text-center mt-8">
          <p className="text-xs text-text-muted">
            For entertainment purposes only. Not gambling advice. Must be 21+ to use. 
            Please gamble responsibly. ParlayGuarantee is an information service and does not accept or place bets.
          </p>
        </div>
      </div>
    </div>
  )
}
