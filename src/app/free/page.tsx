'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function FreePage() {
  const router = useRouter()

  useEffect(() => {
    // Free picks are now assigned on signup — redirect to sign in
    router.replace('/auth/signin')
  }, [router])

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center">
      <div className="text-text-muted">Redirecting to sign up...</div>
    </div>
  )
}
