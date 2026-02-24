import { NextRequest, NextResponse } from 'next/server'
import { createTicket, TicketLeg } from '../../../lib/tickets'

// POST /api/tickets — Create a ticket (called from purchase flow / webhook)
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { user_id, pack_type, stripe_payment_intent_id, legs } = body

    if (!user_id || !pack_type || !stripe_payment_intent_id || !Array.isArray(legs)) {
      return NextResponse.json(
        { error: 'Missing required fields: user_id, pack_type, stripe_payment_intent_id, legs' },
        { status: 400 }
      )
    }

    // Validate legs structure
    const ticketLegs: TicketLeg[] = legs.map((leg: any) => ({
      game_id: leg.game_id || leg.gameId || '',
      team: leg.team || '',
      spread_at_purchase: leg.spread_at_purchase ?? leg.line ?? null,
      bet_type: leg.bet_type || leg.type || 'moneyline',
      odds: leg.odds ?? null,
      sport: leg.sport || '',
      home_team: leg.home_team || leg.homeTeam || '',
      away_team: leg.away_team || leg.awayTeam || '',
      result: null,
      covered: null,
    }))

    const ticket = await createTicket({
      user_id,
      pack_type,
      stripe_payment_intent_id,
      legs: ticketLegs,
    })

    return NextResponse.json({ success: true, ticket })
  } catch (error: any) {
    console.error('Error creating ticket:', error)
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
