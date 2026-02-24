import requests

RESEND_KEY = 're_NEHSMNdA_15YcCrPhJ71LzDbqNdTZw53Y'
BASE_URL = 'https://parlayguarantee.com'

html = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
body{margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.container{max-width:600px;margin:0 auto;background:#111;border-radius:12px;overflow:hidden;border:1px solid #1a1a1a}
.header{background:linear-gradient(135deg,#0d1117,#161b22);padding:32px 24px;text-align:center;border-bottom:2px solid #22c55e}
.logo{font-size:28px;font-weight:800;color:#22c55e;letter-spacing:-0.5px}
.logo span{color:#eab308}
.body{padding:32px 24px;color:#d1d5db;font-size:16px;line-height:1.7}
.body h2{color:#f9fafb;font-size:22px;margin:0 0 16px}
.body p{margin:0 0 16px}
.cta{display:inline-block;background:linear-gradient(135deg,#22c55e,#16a34a);color:#000!important;font-weight:700;font-size:16px;padding:14px 32px;border-radius:8px;text-decoration:none;margin:8px 0 16px}
.highlight{background:#1a2332;border-left:3px solid #22c55e;padding:16px;border-radius:0 8px 8px 0;margin:16px 0}
.footer{padding:24px;text-align:center;color:#6b7280;font-size:12px;border-top:1px solid #1a1a1a}
.footer a{color:#6b7280}
</style></head><body style="background:#0a0a0a;margin:0;padding:0;">
<div style="display:none;max-height:0;overflow:hidden;">Your free AI pick pack is waiting</div>
<div style="padding:20px;"><div class="container">
<div class="header"><div class="logo">Parlay<span>Guarantee</span> 🏆</div></div>
<div class="body">
<h2>Welcome to ParlayGuarantee!</h2>
<p>You've just unlocked something special — a <strong style="color:#22c55e">FREE AI-generated pick pack</strong> crafted by our proprietary model that analyzes thousands of data points in real time.</p>
<div class="highlight">
<strong style="color:#f9fafb">🎁 Your free pack includes:</strong><br>
• AI-curated best bets for today's games<br>
• Confidence ratings for each pick<br>
• Optimal parlay combinations
</div>
<p>Don't let this one sit — today's games won't wait.</p>
<p style="text-align:center"><a href="https://parlayguarantee.com/picks" class="cta">🏈 Claim Your Free Pack →</a></p>
<p style="color:#9ca3af;font-size:14px;">This pack is on us. No credit card required.</p>
</div>
<div class="footer"><p>ParlayGuarantee.com — AI-Powered Sports Picks</p>
<p><a href="https://parlayguarantee.com/unsubscribe">Unsubscribe</a> · <a href="https://parlayguarantee.com">Visit Site</a></p>
</div></div></div></body></html>"""

res = requests.post('https://api.resend.com/emails',
    headers={'Authorization': f'Bearer {RESEND_KEY}', 'Content-Type': 'application/json'},
    json={
        'from': 'ParlayGuarantee <noreply@parlayguarantee.com>',
        'to': ['mybotzee@gmail.com'],
        'subject': '🎉 Welcome! Your FREE Pick Pack is Ready',
        'html': html,
    })
print(res.status_code, res.text)
