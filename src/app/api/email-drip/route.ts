import { NextRequest, NextResponse } from 'next/server';
import { sendDripEmail } from '../../../lib/email-drip';

// POST: Send a specific drip email (triggered by signup or webhook)
export async function POST(request: NextRequest) {
  try {
    const { email, stage } = await request.json();

    if (!email || !stage) {
      return NextResponse.json({ error: 'email and stage required' }, { status: 400 });
    }

    const success = await sendDripEmail(email, stage);

    return NextResponse.json({ success, email, stage });
  } catch (error) {
    console.error('Email drip error:', error);
    return NextResponse.json({ error: 'Failed to send drip email' }, { status: 500 });
  }
}
