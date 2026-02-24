import { NextRequest, NextResponse } from 'next/server'
import { recordPurchase } from '../../../../../engine/db'
import Stripe from 'stripe'

function getStripe() {
  return new Stripe((process.env.STRIPE_SECRET_KEY || '').trim(), {
    apiVersion: '2025-02-24.acacia',
  })
}

export async function POST(req: NextRequest) {
  try {
    const { paymentIntentId, tier, sports, sportsbook } = await req.json()
    if (!paymentIntentId) {
      return NextResponse.json({ error: 'Missing paymentIntentId' }, { status: 400 })
    }

    // Verify with Stripe
    const stripe = getStripe()
    const pi = await stripe.paymentIntents.retrieve(paymentIntentId)

    if (pi.status !== 'succeeded' && pi.status !== 'requires_capture') {
      return NextResponse.json({ error: 'Payment not confirmed' }, { status: 400 })
    }

    const email = pi.metadata.email || pi.receipt_email || ''
    const amount = pi.amount

    recordPurchase({
      email,
      tier: tier || pi.metadata.tier,
      sports: sports || pi.metadata.sports,
      payment_intent_id: paymentIntentId,
      amount,
      status: pi.status === 'succeeded' ? 'charged' : 'authorized',
    })

    return NextResponse.json({ success: true })
  } catch (error: any) {
    console.error('Error recording purchase:', error)
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
