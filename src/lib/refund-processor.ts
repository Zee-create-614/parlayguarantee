// Refund processor — call from result-checking cron/webhook when picks resolve

import Stripe from 'stripe'
import { TIER_CONFIGS, ML_TIER_CONFIGS } from './tier-config'

function getStripe() {
  return new Stripe((process.env.STRIPE_SECRET_KEY || '').trim(), {
    apiVersion: '2026-01-28.clover',
  })
}

/**
 * Process a full refund for a parlay that lost (any leg).
 */
export async function processRefundForLostParlay(paymentIntentId: string): Promise<boolean> {
  try {
    const stripe = getStripe()
    const pi = await stripe.paymentIntents.retrieve(paymentIntentId)

    if (pi.status !== 'succeeded') {
      console.log(`Cannot refund PI ${paymentIntentId} — status: ${pi.status}`)
      return false
    }

    if (pi.latest_charge) {
      const charge = await stripe.charges.retrieve(pi.latest_charge as string)
      if (charge.refunded) {
        console.log(`PI ${paymentIntentId} already refunded`)
        return true
      }
    }

    const tier = pi.metadata.tier
    const config = TIER_CONFIGS[tier] || ML_TIER_CONFIGS[tier]
    const refundAmount = config?.priceInCents || pi.amount

    const refund = await stripe.refunds.create({
      payment_intent: paymentIntentId,
      amount: refundAmount,
      reason: 'requested_by_customer',
      metadata: {
        type: 'parlayguarantee_parlay_loss_refund',
        tier,
        legs: pi.metadata.legs,
        email: pi.metadata.email,
      },
    })

    console.log(`✅ Refund created for ${paymentIntentId}: ${refund.id} — $${refundAmount / 100}`)
    return true
  } catch (error: any) {
    console.error(`Failed to refund ${paymentIntentId}:`, error.message)
    return false
  }
}
