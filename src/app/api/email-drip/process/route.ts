import { NextRequest, NextResponse } from 'next/server';
import { sendDripEmail, getDripStageForSignupDate, DRIP_EMAILS } from '../../../../lib/email-drip';

// This endpoint is called by a daily cron job.
// It accepts a list of users with their signup dates and last drip stage sent,
// then sends the next appropriate drip email to each.
//
// POST body: { users: [{ email, signupDate, lastStageSent }] }
// Or GET with no body: uses the DB to find users (falls back gracefully)

let getAllUsers: (() => any[]) | null = null;
try {
  const db = require('../../../../../engine/db');
  if (db.getAllUsers) getAllUsers = db.getAllUsers;
} catch {}

export async function GET(request: NextRequest) {
  // Cron-compatible: try to load users from DB
  const results: any[] = [];

  if (getAllUsers) {
    try {
      const users = getAllUsers();
      for (const user of users) {
        if (!user.email || !user.created_at) continue;
        const signupDate = new Date(user.created_at);
        const targetStage = getDripStageForSignupDate(signupDate);
        const lastSent = user.drip_stage || 1; // stage 1 sent on signup

        if (targetStage > lastSent) {
          const nextStage = lastSent + 1;
          const success = await sendDripEmail(user.email, nextStage);
          results.push({ email: user.email, stage: nextStage, success });
        }
      }
    } catch (err) {
      console.error('DB error in drip process:', err);
    }
  }

  return NextResponse.json({
    processed: results.length,
    results,
    message: results.length === 0
      ? 'No users need drip emails right now (or DB unavailable — use POST with user list)'
      : `Sent ${results.length} drip emails`,
  });
}

export async function POST(request: NextRequest) {
  try {
    const { users } = await request.json();

    if (!users || !Array.isArray(users)) {
      return NextResponse.json({ error: 'users array required' }, { status: 400 });
    }

    const results = [];

    for (const user of users) {
      const { email, signupDate, lastStageSent = 1 } = user;
      if (!email || !signupDate) continue;

      const targetStage = getDripStageForSignupDate(new Date(signupDate));

      if (targetStage > lastStageSent) {
        const nextStage = lastStageSent + 1;
        const success = await sendDripEmail(email, nextStage);
        results.push({ email, stage: nextStage, success });
      }
    }

    return NextResponse.json({ processed: results.length, results });
  } catch (error) {
    console.error('Drip process error:', error);
    return NextResponse.json({ error: 'Failed to process drip emails' }, { status: 500 });
  }
}
