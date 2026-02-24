import { NextRequest, NextResponse } from 'next/server'
import Stripe from 'stripe'

function getStripe() {
  return new Stripe((process.env.STRIPE_SECRET_KEY || '').trim(), {
    apiVersion: '2026-01-28.clover',
  })
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { email } = body

    const stripe = getStripe()
    const paymentIntent = await stripe.paymentIntents.create({
      amount: 5000, // $50.00
      currency: 'usd',
      capture_method: 'manual',
      metadata: {
        type: 'parlayguarantee_deposit',
        email: email || '',
      },
      ...(email ? { receipt_email: email } : {}),
    })

    return NextResponse.json({
      clientSecret: paymentIntent.client_secret,
      paymentIntentId: paymentIntent.id,
    })
  } catch (error: any) {
    console.error('Error creating payment intent:', error)
    return NextResponse.json(
      { error: error.message || 'Failed to create payment intent' },
      { status: 500 }
    )
  }
}
