import { NextResponse } from 'next/server'
import { getSportsbooks } from '../../../lib/sportsbooks'

export async function GET() {
  const books = await getSportsbooks()
  return NextResponse.json({ sportsbooks: books })
}
