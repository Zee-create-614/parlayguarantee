import { NextRequest, NextResponse } from 'next/server'
import { setRefundStatus, getTicket } from '../../../../../lib/tickets'
import { processRefundForLostParlay } from '../../../../../lib/refund-processor'

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'parlay2026'

// POST /api/admin/refunds/[id] — Approve or deny a refund
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { searchParams } = new URL(req.url)
    const pw = searchParams.get('pw')
    const body = await req.json()
    const bodyPw = body.pw

    if ((pw || bodyPw) !== ADMIN_PASSWORD) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { id } = await params
    const { status, process_stripe } = body

    if (!['approved', 'denied'].includes(status)) {
      return NextResponse.json({ error: 'Status must be approved or denied' }, { status: 400 })
    }

    const ticket = await getTicket(id)
    if (!ticket) {
      return NextResponse.json({ error: 'Ticket not found' }, { status: 404 })
    }

    // Update refund status
    const updated = await setRefundStatus(id, status)

    // If approved and process_stripe is true, trigger Stripe refund
    let stripeRefunded = false
    if (status === 'approved' && process_stripe && ticket.stripe_payment_intent_id) {
      stripeRefunded = await processRefundForLostParlay(ticket.stripe_payment_intent_id)
    }

    return NextResponse.json({
      success: true,
      ticket: updated,
      stripe_refunded: stripeRefunded,
    })
  } catch (error: any) {
    console.error('Error updating refund status:', error)
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
