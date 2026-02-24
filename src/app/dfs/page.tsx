'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function DFSPage() {
  const router = useRouter()

  useEffect(() => {
    async function checkAuth() {
      try {
        const res = await fetch('/api/auth/me')
        const data = await res.json()
        if (!data.authenticated) {
          router.replace('/auth/signin?redirect=/dfs')
        }
      } catch {
        router.replace('/auth/signin?redirect=/dfs')
      }
    }
    checkAuth()
  }, [router])

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center">
      <div className="text-center">
        <div className="text-5xl mb-4">🏗️</div>
        <h1 className="text-2xl font-bold mb-2">DFS Coming Soon</h1>
        <p className="text-text-muted">DFS lineups will be available in a future update.</p>
      </div>
    </div>
  )
}
