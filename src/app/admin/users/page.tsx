'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'

interface User {
  email: string
  name: string
  phone: string
  referralCode: string
  referredBy: string | null
  freePackUsed: boolean
  purchases: number
  credits: number
  signedUp: string
  lastLogin: string
}

interface RecentSignup {
  email: string
  name: string
  at: string
}

interface AdminData {
  totalUsers: number
  recentSignups: RecentSignup[]
  users: User[]
}

export default function AdminUsersPage() {
  const router = useRouter()
  const [data, setData] = useState<AdminData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')

  // Check password from URL
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const pw = urlParams.get('pw')
    if (!pw || pw !== 'parlay2026') {
      router.push('/?error=unauthorized')
      return
    }
    
    // Initial fetch
    fetchData()
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [router])

  const fetchData = async () => {
    try {
      const response = await fetch('/api/admin/users?pw=parlay2026')
      if (!response.ok) {
        throw new Error('Failed to fetch admin data')
      }
      const adminData = await response.json()
      setData(adminData)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (dateStr: string) => {
    if (!dateStr) return 'Never'
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const filteredUsers = data?.users?.filter(user => 
    user.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.phone?.includes(searchTerm)
  ) || []

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-bg-primary via-bg-primary to-bg-secondary flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-accent-green mx-auto"></div>
          <p className="text-text-muted mt-4">Loading admin dashboard...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-bg-primary via-bg-primary to-bg-secondary flex items-center justify-center">
        <div className="text-center text-red-400">
          <p className="text-xl mb-4">Error loading data</p>
          <p className="text-text-muted">{error}</p>
          <button 
            onClick={fetchData}
            className="mt-4 bg-accent-green hover:bg-accent-green/90 text-black font-bold py-2 px-4 rounded"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-bg-primary via-bg-primary to-bg-secondary">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-4xl font-bold text-gradient">
              Admin Users Dashboard
            </h1>
            <div className="text-right">
              <div className="text-sm text-text-muted">Last updated</div>
              <div className="text-accent-green font-mono">
                {new Date().toLocaleTimeString()}
              </div>
            </div>
          </div>
          <p className="text-text-muted">
            User management and analytics for Parlay Guarantee
          </p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="card">
            <div className="text-3xl font-bold text-accent-gold mb-2">
              {data?.totalUsers || 0}
            </div>
            <div className="text-text-muted">Total Users</div>
          </div>
          
          <div className="card">
            <div className="text-3xl font-bold text-accent-green mb-2">
              {data?.recentSignups?.length || 0}
            </div>
            <div className="text-text-muted">Recent Signups</div>
          </div>
          
          <div className="card">
            <div className="text-3xl font-bold text-accent-green mb-2">
              {filteredUsers.filter(u => u.freePackUsed).length}
            </div>
            <div className="text-text-muted">Free Packs Used</div>
          </div>
          
          <div className="card">
            <div className="text-3xl font-bold text-accent-gold mb-2">
              {filteredUsers.reduce((sum, u) => sum + (u.purchases || 0), 0)}
            </div>
            <div className="text-text-muted">Total Purchases</div>
          </div>
        </div>

        {/* Recent Signups */}
        <div className="card mb-8">
          <h2 className="text-2xl font-bold text-accent-green mb-4">
            Recent Signups (Last 20)
          </h2>
          <div className="space-y-2">
            {data?.recentSignups?.map((signup, index) => (
              <div key={index} className="flex justify-between items-center p-3 bg-bg-primary/50 rounded-lg">
                <div>
                  <div className="font-medium text-text-primary">{signup.name || 'Unnamed'}</div>
                  <div className="text-sm text-text-muted">{signup.email}</div>
                </div>
                <div className="text-sm text-accent-gold">
                  {formatDate(signup.at)}
                </div>
              </div>
            )) || (
              <div className="text-text-muted text-center py-4">No recent signups</div>
            )}
          </div>
        </div>

        {/* User Search */}
        <div className="card mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-accent-green">
              All Users ({filteredUsers.length})
            </h2>
            <div className="relative">
              <input
                type="text"
                placeholder="Search users..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="bg-bg-primary border border-accent-green/20 rounded-lg px-4 py-2 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-green"
              />
            </div>
          </div>
          
          {/* Users Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-accent-green/20">
                  <th className="text-left py-3 px-2 text-accent-green">Email</th>
                  <th className="text-left py-3 px-2 text-accent-green">Name</th>
                  <th className="text-left py-3 px-2 text-accent-green">Phone</th>
                  <th className="text-left py-3 px-2 text-accent-green">Referral Code</th>
                  <th className="text-left py-3 px-2 text-accent-green">Free Pack</th>
                  <th className="text-left py-3 px-2 text-accent-green">Purchases</th>
                  <th className="text-left py-3 px-2 text-accent-green">Signed Up</th>
                  <th className="text-left py-3 px-2 text-accent-green">Last Login</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((user, index) => (
                  <tr key={index} className="border-b border-accent-green/10 hover:bg-bg-primary/30">
                    <td className="py-3 px-2 text-text-primary">{user.email}</td>
                    <td className="py-3 px-2 text-text-primary">{user.name || 'N/A'}</td>
                    <td className="py-3 px-2 text-text-muted">{user.phone || 'N/A'}</td>
                    <td className="py-3 px-2 text-accent-gold font-mono">{user.referralCode}</td>
                    <td className="py-3 px-2">
                      <span className={`px-2 py-1 rounded text-xs font-bold ${
                        user.freePackUsed 
                          ? 'bg-accent-green/20 text-accent-green' 
                          : 'bg-accent-gold/20 text-accent-gold'
                      }`}>
                        {user.freePackUsed ? 'Used' : 'Available'}
                      </span>
                    </td>
                    <td className="py-3 px-2 text-text-primary">
                      {user.purchases || 0}
                    </td>
                    <td className="py-3 px-2 text-text-muted">
                      {formatDate(user.signedUp)}
                    </td>
                    <td className="py-3 px-2 text-text-muted">
                      {formatDate(user.lastLogin)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            
            {filteredUsers.length === 0 && (
              <div className="text-center py-8 text-text-muted">
                {searchTerm ? 'No users match your search' : 'No users found'}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="text-center text-text-muted text-sm">
          <p>Auto-refreshes every 30 seconds</p>
          <p className="mt-1">
            <span className="text-accent-green">●</span> Connected to Redis KV Store
          </p>
        </div>
      </div>
    </div>
  )
}