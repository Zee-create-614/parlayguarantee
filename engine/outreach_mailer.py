"""
ParlayGuarantee Outreach Mailer
Batch-send promotional emails via Resend API.

Usage:
  python outreach_mailer.py --template cold_pitch --csv emails.csv [--dry-run]
  python outreach_mailer.py --template affiliate_pitch --csv affiliates.csv
  python outreach_mailer.py --template march_madness_promo --csv emails.csv

CSV format: email column required. Optional: name, subject (override)
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

RESEND_API_KEY = "re_NEHSMNdA_15YcCrPhJ71LzDbqNdTZw53Y"
FROM_EMAIL = "noreply@parlayguarantee.com"
RESEND_URL = "https://api.resend.com/emails"
RATE_LIMIT_SECONDS = 2
DAILY_LIMIT = 100

TEMPLATES_DIR = Path(__file__).parent / "email_templates"

TEMPLATE_SUBJECTS = {
    "cold_pitch": "Free AI Sports Picks — 74% Accuracy Model",
    "affiliate_pitch": "Partner with ParlayGuarantee — AI Picks Platform",
    "march_madness_promo": "🏀 March Madness Picks — Free AI Model Access",
}


def load_template(name: str) -> str:
    path = TEMPLATES_DIR / f"{name}.html"
    if not path.exists():
        print(f"ERROR: Template not found: {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def send_email(to: str, subject: str, html: str, dry_run: bool = False) -> dict:
    payload = {
        "from": FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html,
    }

    if dry_run:
        print(f"  [DRY RUN] Would send to {to}")
        return {"id": "dry-run", "to": to}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RESEND_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"  ✓ Sent to {to} — id: {result.get('id', '?')}")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ✗ Failed for {to}: {e.code} {body}")
        return {"error": e.code, "detail": body, "to": to}


def read_csv(path: str) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row.get("email", "").strip()
            if email:
                rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description="ParlayGuarantee Outreach Mailer")
    parser.add_argument("--template", required=True, choices=list(TEMPLATE_SUBJECTS.keys()))
    parser.add_argument("--csv", required=True, help="Path to CSV with 'email' column")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent without sending")
    parser.add_argument("--limit", type=int, default=DAILY_LIMIT, help=f"Max emails to send (default {DAILY_LIMIT})")
    args = parser.parse_args()

    html = load_template(args.template)
    default_subject = TEMPLATE_SUBJECTS[args.template]
    recipients = read_csv(args.csv)

    if not recipients:
        print("No valid emails found in CSV.")
        sys.exit(1)

    total = min(len(recipients), args.limit)
    print(f"\nTemplate: {args.template}")
    print(f"Subject: {default_subject}")
    print(f"Recipients: {total} of {len(recipients)}")
    print(f"Rate limit: 1 every {RATE_LIMIT_SECONDS}s")
    if args.dry_run:
        print("MODE: DRY RUN\n")
    else:
        print("MODE: LIVE SEND\n")

    sent = 0
    errors = 0

    for i, row in enumerate(recipients[:total]):
        email = row["email"].strip()
        subject = row.get("subject", "").strip() or default_subject

        result = send_email(email, subject, html, dry_run=args.dry_run)
        if "error" in result:
            errors += 1
        else:
            sent += 1

        # Rate limit (skip delay on last email)
        if i < total - 1:
            time.sleep(RATE_LIMIT_SECONDS)

    print(f"\nDone. Sent: {sent}, Errors: {errors}")


if __name__ == "__main__":
    main()
