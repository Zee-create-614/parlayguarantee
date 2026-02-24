import { NextRequest, NextResponse } from 'next/server'
import jwt from 'jsonwebtoken'

const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-key-here'

export async function GET(request: NextRequest) {
  try {
    const cookie = request.cookies.get('parlayguarantee-session')
    if (!cookie) {
      return NextResponse.json({ authenticated: false })
    }
    const decoded = jwt.verify(cookie.value, JWT_SECRET) as any
    if (decoded.type !== 'session') {
      return NextResponse.json({ authenticated: false })
    }
    return NextResponse.json({ 
      authenticated: true, 
      email: decoded.email,
      fullName: decoded.fullName || '',
      freePackUsed: !!decoded.freePackUsed,
    })
  } catch {
    return NextResponse.json({ authenticated: false })
  }
}
