'use client'

import Link from 'next/link'
import Header from '../components/Header'
import { ArrowRight } from 'lucide-react'

export default function CheckoutPage() {
  return (
    <div className="min-h-screen bg-bg-primary">
      <Header />
      <div className="max-w-lg mx-auto px-4 py-32 text-center">
        <div className="text-6xl mb-6">🏀</div>
        <h1 className="text-3xl font-bold mb-4">Picks Launching Soon for March Madness!</h1>
        <p className="text-lg text-text-muted mb-8">
          Sign up for early access to be first in line when we go live.
        </p>
        <Link href="/auth/signin" className="btn-primary text-lg py-4 px-10 inline-flex items-center gap-2">
          Sign Up for Early Access <ArrowRight className="w-5 h-5" />
        </Link>
      </div>
    </div>
  )
}
