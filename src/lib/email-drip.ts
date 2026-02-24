const RESEND_API_KEY = 're_NEHSMNdA_15YcCrPhJ71LzDbqNdTZw53Y';
const FROM_EMAIL = 'ParlayGuarantee <noreply@parlayguarantee.com>';
const BASE_URL = 'https://parlayguarantee.com';

function emailWrapper(content: string, preheader: string = ''): string {
  return `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body { margin:0; padding:0; background:#0a0a0a; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }
  .container { max-width:600px; margin:0 auto; background:#111111; border-radius:12px; overflow:hidden; border:1px solid #1a1a1a; }
  .header { background:linear-gradient(135deg,#0d1117,#161b22); padding:32px 24px; text-align:center; border-bottom:2px solid #22c55e; }
  .logo { font-size:28px; font-weight:800; color:#22c55e; letter-spacing:-0.5px; }
  .logo span { color:#eab308; }
  .body { padding:32px 24px; color:#d1d5db; font-size:16px; line-height:1.7; }
  .body h2 { color:#f9fafb; font-size:22px; margin:0 0 16px; }
  .body p { margin:0 0 16px; }
  .cta { display:inline-block; background:linear-gradient(135deg,#22c55e,#16a34a); color:#000!important; font-weight:700; font-size:16px; padding:14px 32px; border-radius:8px; text-decoration:none; margin:8px 0 16px; }
  .cta.gold { background:linear-gradient(135deg,#eab308,#ca8a04); }
  .highlight { background:#1a2332; border-left:3px solid #22c55e; padding:16px; border-radius:0 8px 8px 0; margin:16px 0; }
  .stat { display:inline-block; text-align:center; padding:12px 20px; }
  .stat-num { font-size:28px; font-weight:800; color:#22c55e; }
  .stat-label { font-size:12px; color:#9ca3af; text-transform:uppercase; }
  .footer { padding:24px; text-align:center; color:#6b7280; font-size:12px; border-top:1px solid #1a1a1a; }
  .footer a { color:#6b7280; }
</style></head>
<body style="background:#0a0a0a;margin:0;padding:0;">
<div style="display:none;max-height:0;overflow:hidden;">${preheader}</div>
<div style="padding:20px;">
<div class="container">
  <div class="header">
    <div class="logo">Parlay<span>Guarantee</span> 🏆</div>
  </div>
  <div class="body">${content}</div>
  <div class="footer">
    <p>ParlayGuarantee.com — AI-Powered Sports Picks</p>
    <p><a href="${BASE_URL}/unsubscribe">Unsubscribe</a> · <a href="${BASE_URL}">Visit Site</a></p>
  </div>
</div>
</div>
</body></html>`;
}

export const DRIP_EMAILS = [
  {
    stage: 1,
    delayHours: 0,
    subject: '🎉 Welcome! Your FREE Pick Pack is Ready',
    html: emailWrapper(`
      <h2>Welcome to ParlayGuarantee!</h2>
      <p>You've just unlocked something special — a <strong style="color:#22c55e">FREE AI-generated pick pack</strong> crafted by our proprietary model that analyzes thousands of data points in real time.</p>
      <div class="highlight">
        <strong style="color:#f9fafb">🎁 Your free pack includes:</strong><br>
        • AI-curated best bets for today's games<br>
        • Confidence ratings for each pick<br>
        • Optimal parlay combinations
      </div>
      <p>Don't let this one sit — today's games won't wait.</p>
      <p style="text-align:center"><a href="${BASE_URL}/picks" class="cta">🏈 Claim Your Free Pack →</a></p>
      <p style="color:#9ca3af;font-size:14px;">This pack is on us. No credit card required.</p>
    `, 'Your free AI pick pack is waiting — claim it now before today\'s games start.'),
  },
  {
    stage: 2,
    delayHours: 24,
    subject: '🤖 The AI Behind Your Picks (72.4% Hit Rate)',
    html: emailWrapper(`
      <h2>How Our AI Model Actually Works</h2>
      <p>You might be wondering — what makes ParlayGuarantee different from every other picks service?</p>
      <p><strong style="color:#22c55e">It's the model.</strong></p>
      <div class="highlight">
        Our AI processes:<br><br>
        📊 <strong>10,000+ data points</strong> per game<br>
        🏥 <strong>Real-time injury reports</strong> & lineup changes<br>
        📈 <strong>Line movement tracking</strong> across 8+ sportsbooks<br>
        🧠 <strong>Historical pattern matching</strong> across 5 seasons<br>
        💰 <strong>Sharp money indicators</strong> & public betting %
      </div>
      <p>The result? Consistent, data-driven picks that don't rely on gut feelings or hot takes.</p>
      <div style="text-align:center;margin:24px 0;">
        <div class="stat"><div class="stat-num">72.4%</div><div class="stat-label">Hit Rate</div></div>
        <div class="stat"><div class="stat-num">+34.2u</div><div class="stat-label">Profit (Units)</div></div>
        <div class="stat"><div class="stat-num">1,200+</div><div class="stat-label">Picks Graded</div></div>
      </div>
      <p style="text-align:center"><a href="${BASE_URL}/results" class="cta">📊 See Full Results →</a></p>
    `, 'Our AI analyzes 10,000+ data points per game. Here\'s how it works.'),
  },
  {
    stage: 3,
    delayHours: 48,
    subject: '⏰ Your Free Pack Expires Soon — Don\'t Miss Out',
    html: emailWrapper(`
      <h2>Your Free Pack is About to Expire</h2>
      <p>Hey — just a heads up. The <strong style="color:#eab308">free pick pack</strong> we gave you is expiring soon.</p>
      <p>Once it's gone, it's gone. We can't hold it forever.</p>
      <div class="highlight" style="border-left-color:#eab308;">
        <strong style="color:#eab308">⚠️ Don't leave money on the table.</strong><br><br>
        Members who used their free pack last week hit at a <strong style="color:#22c55e">68% clip</strong>. That's real profit from a free product.
      </div>
      <p>It takes 30 seconds to check your picks. No strings attached.</p>
      <p style="text-align:center"><a href="${BASE_URL}/picks" class="cta gold">⏰ Use Your Free Pack Now →</a></p>
      <p style="color:#9ca3af;font-size:14px;text-align:center;">After expiration, packs start at just $5.</p>
    `, 'Your free pick pack expires soon. Use it before it\'s gone.'),
  },
  {
    stage: 4,
    delayHours: 72,
    subject: '🔥 "I turned $5 into $180" — Real Member Results',
    html: emailWrapper(`
      <h2>People Are Cashing In</h2>
      <p>Don't just take our word for it. Here's what ParlayGuarantee members are saying:</p>
      <div class="highlight">
        <p style="margin:0 0 12px;"><strong style="color:#22c55e">"Hit a 4-leg parlay on my first pack. $5 → $180."</strong><br><span style="color:#9ca3af">— Mike T., Ohio</span></p>
        <p style="margin:0 0 12px;"><strong style="color:#22c55e">"Best $5 I've ever spent. 3/4 legs hit."</strong><br><span style="color:#9ca3af">— Sarah K., Florida</span></p>
        <p style="margin:0;"><strong style="color:#22c55e">"The AI picks are scary accurate. I'm hooked."</strong><br><span style="color:#9ca3af">— Dre W., Texas</span></p>
      </div>
      <p>Your first paid pack is just <strong style="color:#eab308;font-size:20px;">$5</strong>. That's less than your morning coffee — and it could pay for your whole week.</p>
      <p style="text-align:center"><a href="${BASE_URL}/pricing" class="cta gold">💰 Get Your $5 Pack →</a></p>
    `, 'Real members are cashing in. Your first pack is just $5.'),
  },
  {
    stage: 5,
    delayHours: 168,
    subject: '🏀 March Madness is Coming — Lock In Now',
    html: emailWrapper(`
      <h2>March Madness is Almost Here 🏀</h2>
      <p>The most exciting (and most profitable) time in sports betting is right around the corner.</p>
      <p><strong style="color:#22c55e">March Madness = chaos.</strong> Upsets. Cinderella runs. And massive parlay opportunities.</p>
      <div class="highlight">
        <strong style="color:#f9fafb">Last year during the tournament:</strong><br><br>
        🏆 Our model hit <strong style="color:#22c55e">74.1%</strong> of tournament picks<br>
        💰 Members averaged <strong style="color:#22c55e">+8.3 units</strong> profit<br>
        🎯 We called 3 of the Final Four teams correctly
      </div>
      <p>This year's model is even better. More data. Sharper algorithms. Better edges.</p>
      <p><strong>Don't watch from the sidelines.</strong></p>
      <p style="text-align:center"><a href="${BASE_URL}/pricing" class="cta">🏀 Get Tournament Ready →</a></p>
      <p style="color:#9ca3af;font-size:14px;text-align:center;">Packs start at $5. Tournament bundles coming soon.</p>
    `, 'March Madness is coming. Our AI model crushed it last year — get ready.'),
  },
];

export async function sendDripEmail(to: string, stage: number): Promise<boolean> {
  const email = DRIP_EMAILS.find(e => e.stage === stage);
  if (!email) return false;

  try {
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: FROM_EMAIL,
        to: [to],
        subject: email.subject,
        html: email.html,
      }),
    });

    if (!res.ok) {
      const err = await res.text();
      console.error(`Drip email stage ${stage} failed for ${to}:`, err);
      return false;
    }
    console.log(`Drip email stage ${stage} sent to ${to}`);
    return true;
  } catch (err) {
    console.error(`Drip email error:`, err);
    return false;
  }
}

export function getDripStageForSignupDate(signupDate: Date): number {
  const now = Date.now();
  const elapsed = now - signupDate.getTime();
  const hours = elapsed / (1000 * 60 * 60);

  if (hours >= 168) return 5;
  if (hours >= 72) return 4;
  if (hours >= 48) return 3;
  if (hours >= 24) return 2;
  return 1;
}
