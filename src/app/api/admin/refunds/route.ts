import { NextRequest, NextResponse } from 'next/server'
import { listTickets } from '../../../../lib/tickets'

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'parlay2026'

// GET /api/admin/refunds — List all tickets with refund info
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const pw = searchParams.get('pw')

  if (pw !== ADMIN_PASSWORD) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    const { tickets, total } = await listTickets({
      limit: parseInt(searchParams.get('limit') || '100'),
      offset: parseInt(searchParams.get('offset') || '0'),
      pack_type: searchParams.get('pack_type') || undefined,
      refund_status: searchParams.get('refund_status') || undefined,
      date_from: searchParams.get('date_from') || undefined,
      date_to: searchParams.get('date_to') || undefined,
    })

    // Summary stats
    const stats = {
      total: tickets.length,
      pending: tickets.filter(t => t.refund_status === 'pending').length,
      approved: tickets.filter(t => t.refund_status === 'approved').length,
      denied: tickets.filter(t => t.refund_status === 'denied').length,
      eligible: tickets.filter(t => t.refund_eligible === true).length,
      not_eligible: tickets.filter(t => t.refund_eligible === false).length,
      unscored: tickets.filter(t => t.refund_eligible === null).length,
    }

    return NextResponse.json({ tickets, stats, total })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
