"""
Drip email processor — queries Upstash Redis for users, sends due drip emails via Resend.
Tracks drip_stage per user in Redis key: drip:<email>
"""
import requests, json, os, sys
from datetime import datetime, timezone

RESEND_KEY = 're_NEHSMNdA_15YcCrPhJ71LzDbqNdTZw53Y'
FROM_EMAIL = 'ParlayGuarantee <noreply@parlayguarantee.com>'
BASE_URL = 'https://parlayguarantee.com'

UPSTASH_URL = 'https://vocal-crawdad-5028.upstash.io'
UPSTASH_TOKEN = 'AROkAAImcDFiNGU4YjJlYjI3NjM0ODEzYmUwNmY3ZjE1MzgzMjI5MnAxNTAyOA'

# Stage: hours after signup
STAGES = [(1, 0), (2, 24), (3, 48), (4, 72), (5, 168)]

SUBJECTS = {
    1: '🎉 Welcome! Your FREE Pick Pack is Ready',
    2: '🤖 The AI Behind Your Picks (72.4% Hit Rate)',
    3: "⏰ Your Free Pack Expires Soon — Don't Miss Out",
    4: '🔥 "I turned $5 into $180" — Real Member Results',
    5: '🏀 March Madness is Coming — Lock In Now',
}

def wrap(content, preheader=''):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>body{{margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}}.container{{max-width:600px;margin:0 auto;background:#111;border-radius:12px;overflow:hidden;border:1px solid #1a1a1a}}.header{{background:linear-gradient(135deg,#0d1117,#161b22);padding:32px 24px;text-align:center;border-bottom:2px solid #22c55e}}.logo{{font-size:28px;font-weight:800;color:#22c55e;letter-spacing:-0.5px}}.logo span{{color:#eab308}}.body{{padding:32px 24px;color:#d1d5db;font-size:16px;line-height:1.7}}.body h2{{color:#f9fafb;font-size:22px;margin:0 0 16px}}.body p{{margin:0 0 16px}}.cta{{display:inline-block;background:linear-gradient(135deg,#22c55e,#16a34a);color:#000!important;font-weight:700;font-size:16px;padding:14px 32px;border-radius:8px;text-decoration:none;margin:8px 0 16px}}.cta.gold{{background:linear-gradient(135deg,#eab308,#ca8a04)}}.highlight{{background:#1a2332;border-left:3px solid #22c55e;padding:16px;border-radius:0 8px 8px 0;margin:16px 0}}.footer{{padding:24px;text-align:center;color:#6b7280;font-size:12px;border-top:1px solid #1a1a1a}}.footer a{{color:#6b7280}}</style></head>
<body style="background:#0a0a0a;margin:0;padding:0;"><div style="display:none;max-height:0;overflow:hidden;">{preheader}</div>
<div style="padding:20px;"><div class="container"><div class="header"><div class="logo">Parlay<span>Guarantee</span> 🏆</div></div>
<div class="body">{content}</div>
<div class="footer"><p>ParlayGuarantee.com — AI-Powered Sports Picks</p><p><a href="{BASE_URL}/unsubscribe">Unsubscribe</a> · <a href="{BASE_URL}">Visit Site</a></p></div></div></div></body></html>"""

BODIES = {
    1: wrap(f'<h2>Welcome to ParlayGuarantee!</h2><p>You\'ve just unlocked a <strong style="color:#22c55e">FREE AI-generated pick pack</strong> crafted by our proprietary model.</p><div class="highlight"><strong style="color:#f9fafb">🎁 Your free pack includes:</strong><br>• AI-curated best bets<br>• Confidence ratings<br>• Optimal parlay combos</div><p style="text-align:center"><a href="{BASE_URL}/picks" class="cta">🏈 Claim Your Free Pack →</a></p>', "Your free AI pick pack is waiting"),
    2: wrap(f'<h2>How Our AI Model Actually Works</h2><p><strong style="color:#22c55e">It\'s the model.</strong></p><div class="highlight">📊 <strong>10,000+ data points</strong> per game<br>🏥 <strong>Real-time injuries</strong><br>📈 <strong>Line movement</strong> across 8+ books<br>🧠 <strong>5 seasons</strong> of pattern matching<br>💰 <strong>Sharp money</strong> indicators</div><p style="text-align:center"><a href="{BASE_URL}/results" class="cta">📊 See Full Results →</a></p>', "10,000+ data points per game."),
    3: wrap(f'<h2>Your Free Pack is About to Expire</h2><p>The <strong style="color:#eab308">free pick pack</strong> we gave you is expiring soon.</p><div class="highlight" style="border-left-color:#eab308;"><strong style="color:#eab308">⚠️ Don\'t leave money on the table.</strong><br>Members hit at a <strong style="color:#22c55e">68% clip</strong> last week.</div><p style="text-align:center"><a href="{BASE_URL}/picks" class="cta gold">⏰ Use Your Free Pack Now →</a></p>', "Your free pack expires soon."),
    4: wrap(f'<h2>People Are Cashing In</h2><div class="highlight"><p style="margin:0 0 12px;"><strong style="color:#22c55e">"$5 → $180 on my first pack."</strong><br><span style="color:#9ca3af">— Mike T., Ohio</span></p><p style="margin:0;"><strong style="color:#22c55e">"The AI picks are scary accurate."</strong><br><span style="color:#9ca3af">— Dre W., Texas</span></p></div><p>First pack: <strong style="color:#eab308;font-size:20px;">$5</strong></p><p style="text-align:center"><a href="{BASE_URL}/pricing" class="cta gold">💰 Get Your $5 Pack →</a></p>', "Real members are cashing in."),
    5: wrap(f'<h2>March Madness is Almost Here 🏀</h2><p><strong style="color:#22c55e">Chaos = opportunity.</strong></p><div class="highlight">🏆 <strong style="color:#22c55e">74.1%</strong> tournament hit rate<br>💰 <strong style="color:#22c55e">+8.3 units</strong> avg profit<br>🎯 3 of 4 Final Four teams called</div><p style="text-align:center"><a href="{BASE_URL}/pricing" class="cta">🏀 Get Tournament Ready →</a></p>', "March Madness is coming."),
}

def redis_cmd(*args):
    """Execute a Redis command via Upstash REST API."""
    r = requests.post(f'{UPSTASH_URL}', 
        headers={'Authorization': f'Bearer {UPSTASH_TOKEN}', 'Content-Type': 'application/json'},
        json=list(args))
    r.raise_for_status()
    return r.json().get('result')

def get_all_user_emails():
    """Get all user emails from the users:all sorted set."""
    return redis_cmd('ZRANGE', 'users:all', '0', '-1') or []

def get_user(email):
    """Get user data from Redis."""
    data = redis_cmd('GET', f'user:{email}')
    if data and isinstance(data, str):
        return json.loads(data)
    return data

def get_drip_stage(email):
    """Get last drip stage sent (stored in drip:<email>)."""
    val = redis_cmd('GET', f'drip:{email}')
    return int(val) if val else 0

def set_drip_stage(email, stage):
    redis_cmd('SET', f'drip:{email}', str(stage))

def send_email(to, stage):
    res = requests.post('https://api.resend.com/emails',
        headers={'Authorization': f'Bearer {RESEND_KEY}', 'Content-Type': 'application/json'},
        json={'from': FROM_EMAIL, 'to': [to], 'subject': SUBJECTS[stage], 'html': BODIES[stage]})
    return res.status_code == 200

import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    emails = get_all_user_emails()
    print(f"Found {len(emails)} users in Upstash")
    
    sent = 0
    for email in emails:
        user = get_user(email)
        if not user:
            continue
        
        signup_str = user.get('createdAt', '')
        if not signup_str:
            continue
        
        try:
            signup = datetime.fromisoformat(signup_str.replace('Z', '+00:00'))
        except:
            continue
        
        hours_since = (datetime.now(timezone.utc) - signup).total_seconds() / 3600
        last_stage = get_drip_stage(email)
        
        # Find the highest due stage
        due = None
        for stage, delay in STAGES:
            if stage > last_stage and hours_since >= delay:
                due = stage
        
        if due:
            # Stage 1 is already sent on signup by verify-magic, so skip if last_stage == 0
            # Actually, set their drip to 1 if they have none tracked yet, then send next due
            if last_stage == 0:
                set_drip_stage(email, 1)
                if due == 1:
                    print(f"⏭️  {email} — stage 1 already sent on signup, marking")
                    continue
                # They're due for stage 2+, send it
            
            ok = send_email(email, due)
            if ok:
                set_drip_stage(email, due)
                sent += 1
                print(f"✅ Stage {due} → {email} (signed up {hours_since:.0f}h ago)")
            else:
                print(f"❌ Failed stage {due} → {email}")
        else:
            status = "complete" if last_stage >= 5 else f"stage {last_stage}, next in {STAGES[last_stage][1] if last_stage < 5 else 'n/a'}h"
            print(f"⏸️  {email} — {status}")
    
    print(f"\n📧 Drip Processor: {sent} emails sent, {len(emails)} users total.")

if __name__ == '__main__':
    main()
