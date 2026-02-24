'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function PicksPage() {
  const router = useRouter()

  useEffect(() => {
    // Picks are private — redirect to dashboard (which requires auth)
    router.replace('/dashboard')
  }, [router])

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center">
      <div className="text-text-muted">Redirecting to dashboard...</div>
    </div>
  )
}
