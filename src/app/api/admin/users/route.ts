import { NextRequest, NextResponse } from 'next/server'
import { getAllUsers, getUser, getUserCount, getRecentSignups } from '../../../../lib/kv'
import { initializeDatabase, getClient } from '../../../../../engine/db'

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'parlay2026'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const pw = searchParams.get('pw')

  if (pw !== ADMIN_PASSWORD) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    let totalUsers = 0
    let recentSignups: any[] = []
    let users: any[] = []

    // Try Turso database first
    try {
      await initializeDatabase()
      const client = getClient()

      // Get total users
      const totalResult = await client.execute('SELECT COUNT(*) as count FROM users')
      totalUsers = Number(totalResult.rows[0]?.count) || 0

      // Get recent signups (last 20)
      const recentResult = await client.execute(`
        SELECT email, created_at
        FROM users 
        ORDER BY created_at DESC 
        LIMIT 20
      `)
      
      recentSignups = recentResult.rows.map((row: any) => ({
        email: row.email,
        name: '', // We don't store full names in the database
        at: row.created_at
      }))

      // Get all users (limit 100 for performance)
      const usersResult = await client.execute(`
        SELECT 
          email,
          free_pack_used,
          referral_code,
          referred_by,
          referral_credits,
          packs_purchased,
          created_at
        FROM users 
        ORDER BY created_at DESC 
        LIMIT 100
      `)

      users = usersResult.rows.map((row: any) => ({
        email: row.email,
        name: '', // Not stored in Turso DB
        phone: '', // Not stored in Turso DB
        referralCode: row.referral_code,
        referredBy: row.referred_by,
        freePackUsed: Boolean(row.free_pack_used),
        purchases: Number(row.packs_purchased) || 0,
        credits: Number(row.referral_credits) || 0,
        signedUp: row.created_at,
        lastLogin: '', // Not tracked in Turso DB yet
      }))

    } catch (dbErr) {
      console.warn('Turso DB failed, falling back to KV:', dbErr)

      // Fallback to KV store
      totalUsers = await getUserCount()
      recentSignups = await getRecentSignups(20)
      const userEmails = await getAllUsers(50)

      // Fetch full user objects from KV
      users = await Promise.all(
        userEmails.map(async (email: string) => {
          const user = await getUser(email)
          if (!user) return { email }
          return {
            email: user.email,
            name: user.fullName,
            phone: user.phone,
            referralCode: user.referralCode,
            referredBy: user.referredBy,
            freePackUsed: user.freePackUsed,
            purchases: user.purchaseCount,
            credits: user.referralCredits,
            signedUp: user.createdAt,
            lastLogin: user.lastLogin,
          }
        })
      )
    }

    return NextResponse.json({
      totalUsers,
      recentSignups,
      users,
      source: users.length > 0 && users[0].name ? 'kv' : 'turso'
    })
  } catch (error: any) {
    console.error('Admin users API error:', error)
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}