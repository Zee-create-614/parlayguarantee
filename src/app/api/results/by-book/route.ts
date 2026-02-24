import { NextResponse } from 'next/server'

// Aggregates results grouped by sportsbook
// For now, returns placeholder data since per-book tracking is just starting
// Future: read from results.db (local) or KV results:export (Vercel)

export async function GET() {
  // No per-book results yet — return empty so homepage handles gracefully
  return NextResponse.json({
    books: [],
    message: 'Live per-sportsbook tracking starts now. Results coming soon.',
  })
}
