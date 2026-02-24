import { NextRequest, NextResponse } from 'next/server'
import Stripe from 'stripe'
import { createTicket, TicketLeg } from '../../../lib/tickets'
// Tier config imported for reference; refund logic lives in src/lib/refund-processor.ts

function getStripe() {
  return new Stripe((process.env.STRIPE_SECRET_KEY || '').trim(), {
    apiVersion: '2026-01-28.clover',
  })
}

export async function POST(req: NextRequest) {
  const body = await req.text()
  const sig = req.headers.get('stripe-signature')

  if (!sig || !process.env.STRIPE_WEBHOOK_SECRET) {
    return NextResponse.json({ error: 'Missing signature or secret' }, { status: 400 })
  }

  let event: Stripe.Event
  try {
    const stripe = getStripe()
    event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET)
  } catch (err: any) {
    console.error('Webhook signature verification failed:', err.message)
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 })
  }

  const stripe = getStripe()

  switch (event.type) {
    case 'payment_intent.succeeded': {
      const pi = event.data.object as Stripe.PaymentIntent
      const tier = pi.metadata.tier
      const email = pi.metadata.email
      const legs = pi.metadata.legs
      const pickIds = pi.metadata.pick_ids

      console.log(`✅ Payment succeeded: ${pi.id} — $${pi.amount / 100} (${tier}, ${legs} legs)`)
      console.log(`   Email: ${email}, Picks: ${pickIds}`)

      // Create ticket with frozen line snapshot
      try {
        let parlayData: any = null
        try {
          parlayData = JSON.parse(pi.metadata.parlay_data || '{}')
        } catch {}

        const ticketLegs: TicketLeg[] = (parlayData?.legs || []).map((leg: any) => ({
          game_id: leg.gameId || '',
          team: leg.team || '',
          spread_at_purchase: leg.line ?? null,
          bet_type: leg.type || 'moneyline',
          odds: leg.odds || null,
          sport: leg.sport || '',
          home_team: leg.homeTeam || '',
          away_team: leg.awayTeam || '',
          result: null,
          covered: null,
        }))

        if (ticketLegs.length > 0 && email) {
          await createTicket({
            user_id: email,
            pack_type: tier || 'unknown',
            stripe_payment_intent_id: pi.id,
            legs: ticketLegs,
          })
          console.log(`🎫 Ticket created for ${email} — ${tier}, ${ticketLegs.length} legs`)
        }
      } catch (ticketErr: any) {
        console.error('Failed to create ticket:', ticketErr.message)
      }

      // TODO: Send confirmation email with pick details
      // TODO: Schedule result checking for these picks
      break
    }

    case 'charge.refunded': {
      const charge = event.data.object as Stripe.Charge
      console.log(`💸 Refund processed: ${charge.id} — $${(charge.amount_refunded || 0) / 100}`)
      // TODO: Send refund confirmation email
      break
    }

    // ─── Auto-capture: completes the auth+capture flow ───
    // When capture_method is 'manual', Stripe fires this event after authorization.
    // We immediately capture so payment_intent.succeeded fires next → ticket creation.
    // NOTE: Ensure 'payment_intent.amount_capturable_updated' is enabled in your
    // Stripe Dashboard → Developers → Webhooks → select endpoint → Add events.
    case 'payment_intent.amount_capturable_updated': {
      const pi = event.data.object as Stripe.PaymentIntent
      console.log(`💳 Authorization hold placed: ${pi.id} — $${pi.amount / 100}. Auto-capturing...`)
      try {
        const captured = await stripe.paymentIntents.capture(pi.id)
        console.log(`✅ Auto-captured ${captured.id} — $${captured.amount / 100}`)
      } catch (captureErr: any) {
        console.error(`❌ Auto-capture failed for ${pi.id}:`, captureErr.message)
        // Don't return error — Stripe will retry the webhook
      }
      break
    }

    case 'payment_intent.canceled': {
      const pi = event.data.object as Stripe.PaymentIntent
      console.log(`❌ Payment canceled: ${pi.id}`)
      break
    }

    default:
      console.log(`Unhandled event: ${event.type}`)
  }

  return NextResponse.json({ received: true })
}

// Refund processing logic: see src/lib/refund-processor.ts
