"""
ParlayGuarantee Roster Tracker
Tracks NBA trades/injuries/acquisitions AND NCAAB transfers/seniors/freshmen.
Sources: ESPN, CBS Sports, 247Sports.
Stores events with impact assessment. Engine auto-adjusts team strength.

Usage:
    python roster_tracker.py --update                  # fetch latest events
    python roster_tracker.py --update --sport NCAAB
    python roster_tracker.py --team "Boston Celtics"   # show team events
    python roster_tracker.py --impact                  # show all active adjustments
    python roster_tracker.py --recent 7                # events from last 7 days
"""

import sys
import json
import sqlite3
import logging
import argparse
import requests
import re
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "learning.db"

# ESPN transaction/injury endpoints
ESPN_NBA_TRANSACTIONS = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/transactions"
ESPN_NBA_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
ESPN_NCAAB_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/injuries"

# Impact multipliers by event type
IMPACT_WEIGHTS = {
    # NBA
    'trade': 0.15,
    'signing': 0.08,
    'waiver': 0.05,
    'injury_out': 0.20,
    'injury_doubtful': 0.15,
    'injury_questionable': 0.08,
    'injury_probable': 0.03,
    'injury_return': -0.12,     # positive impact (returning)
    'suspension': 0.12,
    # NCAAB
    'transfer_in': 0.10,
    'transfer_out': -0.10,
    'senior_leaving': -0.08,
    'freshman_arrival': 0.06,
    'coach_change': 0.20,
}

# Star player multiplier (estimated by role)
STAR_MULTIPLIERS = {
    'superstar': 2.5,   # top-10 player
    'allstar': 1.8,
    'starter': 1.0,
    'rotation': 0.5,
    'bench': 0.2,
}


class RosterTracker:
    """Tracks roster changes and computes team strength adjustments."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS roster_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                sport TEXT NOT NULL,
                team TEXT NOT NULL,
                player TEXT,
                event_type TEXT NOT NULL,
                description TEXT,
                source TEXT,
                impact_score REAL,
                player_tier TEXT,         -- 'superstar', 'allstar', 'starter', etc.
                duration_days INTEGER,    -- expected duration (injuries)
                expires_at TEXT,          -- when adjustment stops applying
                active INTEGER DEFAULT 1,
                raw_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(event_date, team, player, event_type)
            );

            CREATE INDEX IF NOT EXISTS idx_roster_team ON roster_events(team);
            CREATE INDEX IF NOT EXISTS idx_roster_active ON roster_events(active);
            CREATE INDEX IF NOT EXISTS idx_roster_sport ON roster_events(sport);

            CREATE TABLE IF NOT EXISTS team_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team TEXT NOT NULL,
                sport TEXT NOT NULL,
                adjustment REAL NOT NULL,
                reason TEXT,
                computed_at TEXT DEFAULT (datetime('now')),
                UNIQUE(team, sport)
            );
        """)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------
    def fetch_nba_injuries(self) -> List[Dict]:
        """Fetch current NBA injuries from ESPN."""
        events = []
        try:
            resp = requests.get(ESPN_NBA_INJURIES, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for team_data in data.get('items', data.get('injuries', [])):
                # ESPN injury format varies; handle both structures
                team_name = None
                injuries = []

                if isinstance(team_data, dict):
                    team_info = team_data.get('team', {})
                    team_name = team_info.get('displayName', team_info.get('name', ''))
                    injuries = team_data.get('injuries', [])

                for inj in injuries:
                    player_name = ''
                    athlete = inj.get('athlete', {})
                    if isinstance(athlete, dict):
                        player_name = athlete.get('displayName', athlete.get('fullName', ''))

                    status = inj.get('status', inj.get('type', {}).get('name', '')).lower()
                    description = inj.get('details', {}).get('detail', inj.get('longComment', ''))

                    event_type = 'injury_questionable'
                    if 'out' in status:
                        event_type = 'injury_out'
                    elif 'doubtful' in status:
                        event_type = 'injury_doubtful'
                    elif 'probable' in status or 'day-to-day' in status:
                        event_type = 'injury_probable'

                    events.append({
                        'event_date': date.today().isoformat(),
                        'sport': 'NBA',
                        'team': team_name,
                        'player': player_name,
                        'event_type': event_type,
                        'description': description or status,
                        'source': 'ESPN',
                    })

            logger.info(f"Fetched {len(events)} NBA injury entries from ESPN")
        except Exception as e:
            logger.error(f"Failed to fetch NBA injuries: {e}")

        return events

    def fetch_nba_transactions(self) -> List[Dict]:
        """Fetch recent NBA transactions from ESPN."""
        events = []
        try:
            resp = requests.get(ESPN_NBA_TRANSACTIONS, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get('items', data.get('transactions', [])):
                team_name = ''
                team_info = item.get('team', {})
                if isinstance(team_info, dict):
                    team_name = team_info.get('displayName', '')

                description = item.get('text', item.get('description', ''))
                tx_date = item.get('date', date.today().isoformat())

                # Classify transaction type
                desc_lower = description.lower()
                if 'trade' in desc_lower or 'acquired' in desc_lower:
                    event_type = 'trade'
                elif 'sign' in desc_lower:
                    event_type = 'signing'
                elif 'waiv' in desc_lower or 'release' in desc_lower:
                    event_type = 'waiver'
                elif 'suspend' in desc_lower:
                    event_type = 'suspension'
                else:
                    event_type = 'trade'

                # Try to extract player name
                player = ''
                # Common pattern: "Traded G John Smith to ..."
                match = re.search(r'(?:traded|signed|waived|released|acquired)\s+\w+\s+([\w\.\s]+?)(?:\s+to|\s+from|\.|$)', desc_lower)
                if match:
                    player = match.group(1).strip().title()

                events.append({
                    'event_date': tx_date[:10] if tx_date else date.today().isoformat(),
                    'sport': 'NBA',
                    'team': team_name,
                    'player': player,
                    'event_type': event_type,
                    'description': description,
                    'source': 'ESPN',
                })

            logger.info(f"Fetched {len(events)} NBA transactions from ESPN")
        except Exception as e:
            logger.error(f"Failed to fetch NBA transactions: {e}")

        return events

    def fetch_ncaab_injuries(self) -> List[Dict]:
        """Fetch current NCAAB injuries from ESPN."""
        events = []
        try:
            resp = requests.get(ESPN_NCAAB_INJURIES, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for team_data in data.get('items', data.get('injuries', [])):
                if not isinstance(team_data, dict):
                    continue
                team_info = team_data.get('team', {})
                team_name = team_info.get('displayName', team_info.get('name', ''))

                for inj in team_data.get('injuries', []):
                    athlete = inj.get('athlete', {})
                    player_name = athlete.get('displayName', '') if isinstance(athlete, dict) else ''
                    status = inj.get('status', '').lower()

                    event_type = 'injury_questionable'
                    if 'out' in status:
                        event_type = 'injury_out'
                    elif 'doubtful' in status:
                        event_type = 'injury_doubtful'

                    events.append({
                        'event_date': date.today().isoformat(),
                        'sport': 'NCAAB',
                        'team': team_name,
                        'player': player_name,
                        'event_type': event_type,
                        'description': inj.get('details', {}).get('detail', status),
                        'source': 'ESPN',
                    })

            logger.info(f"Fetched {len(events)} NCAAB injury entries from ESPN")
        except Exception as e:
            logger.error(f"Failed to fetch NCAAB injuries: {e}")

        return events

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    def store_event(self, event: Dict) -> bool:
        """Store a roster event. Returns True if new (not duplicate)."""
        impact = self._compute_impact(event)
        c = self.conn.cursor()
        try:
            c.execute("""
                INSERT OR IGNORE INTO roster_events
                (event_date, sport, team, player, event_type, description, source,
                 impact_score, player_tier, duration_days, active, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                event.get('event_date'), event.get('sport', 'NBA'),
                event.get('team'), event.get('player'),
                event.get('event_type'), event.get('description'),
                event.get('source'), impact,
                event.get('player_tier', 'starter'),
                event.get('duration_days'),
                json.dumps(event),
            ))
            self.conn.commit()
            return c.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to store event: {e}")
            return False

    def _compute_impact(self, event: Dict) -> float:
        """Compute impact score for an event."""
        base = IMPACT_WEIGHTS.get(event.get('event_type', ''), 0.05)
        tier = event.get('player_tier', 'starter')
        multiplier = STAR_MULTIPLIERS.get(tier, 1.0)
        return round(base * multiplier, 4)

    # ------------------------------------------------------------------
    # Team strength adjustments
    # ------------------------------------------------------------------
    def compute_team_adjustments(self, sport: str = 'NBA') -> Dict[str, float]:
        """
        Compute net strength adjustment for each team based on active roster events.
        Returns {team: adjustment} where negative = weaker, positive = stronger.
        """
        c = self.conn.cursor()
        rows = c.execute("""
            SELECT team, SUM(impact_score) as total_impact
            FROM roster_events
            WHERE active = 1 AND sport = ?
            GROUP BY team
        """, (sport,)).fetchall()

        adjustments = {}
        for row in rows:
            team = row['team']
            # Injuries are negative (impact_score is positive for injuries),
            # returns are negative impact_score (positive for team)
            raw = row['total_impact']
            # Clamp adjustment to reasonable range (-0.25 to +0.10)
            adj = max(-0.25, min(0.10, -raw))
            adjustments[team] = round(adj, 4)

        # Persist
        for team, adj in adjustments.items():
            c.execute("""
                INSERT OR REPLACE INTO team_adjustments (team, sport, adjustment, reason)
                VALUES (?, ?, ?, ?)
            """, (team, sport, adj, f"Net of {len(rows)} active roster events"))
        self.conn.commit()

        return adjustments

    def get_team_adjustment(self, team: str, sport: str = 'NBA') -> float:
        """Get the current strength adjustment for a team."""
        c = self.conn.cursor()
        row = c.execute("""
            SELECT adjustment FROM team_adjustments
            WHERE team = ? AND sport = ?
        """, (team, sport)).fetchone()
        return row['adjustment'] if row else 0.0

    def get_team_events(self, team: str, active_only: bool = True) -> List[Dict]:
        """Get all roster events for a team."""
        c = self.conn.cursor()
        where = "team = ?"
        params = [team]
        if active_only:
            where += " AND active = 1"
        rows = c.execute(f"""
            SELECT * FROM roster_events WHERE {where}
            ORDER BY event_date DESC
        """, params).fetchall()
        return [dict(r) for r in rows]

    def expire_old_events(self, days: int = 30):
        """Deactivate events older than N days."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        c = self.conn.cursor()
        c.execute("""
            UPDATE roster_events SET active = 0
            WHERE event_date < ? AND active = 1 AND event_type NOT LIKE 'injury_%'
        """, (cutoff,))
        # Deactivate injury_probable after 3 days
        prob_cutoff = (date.today() - timedelta(days=3)).isoformat()
        c.execute("""
            UPDATE roster_events SET active = 0
            WHERE event_date < ? AND active = 1 AND event_type = 'injury_probable'
        """, (prob_cutoff,))
        self.conn.commit()
        logger.info(f"Expired old roster events (cutoff: {cutoff})")

    # ------------------------------------------------------------------
    # Update all
    # ------------------------------------------------------------------
    def update(self, sport: str = 'NBA') -> Dict:
        """Fetch and store latest roster events. Returns summary."""
        self.expire_old_events()

        events = []
        if sport in ('NBA', 'ALL'):
            events.extend(self.fetch_nba_injuries())
            events.extend(self.fetch_nba_transactions())
        if sport in ('NCAAB', 'ALL'):
            events.extend(self.fetch_ncaab_injuries())

        new_count = 0
        for ev in events:
            if self.store_event(ev):
                new_count += 1

        adjustments = self.compute_team_adjustments(sport if sport != 'ALL' else 'NBA')
        if sport == 'ALL':
            adjustments.update(self.compute_team_adjustments('NCAAB'))

        summary = {
            'sport': sport,
            'events_fetched': len(events),
            'new_events': new_count,
            'teams_with_adjustments': len(adjustments),
            'updated_at': datetime.now().isoformat(),
        }

        logger.info(f"Roster update: {len(events)} fetched, {new_count} new, "
                     f"{len(adjustments)} team adjustments computed")
        return summary

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='ParlayGuarantee Roster Tracker')
    parser.add_argument('--update', action='store_true', help='Fetch latest roster events')
    parser.add_argument('--sport', type=str, default='NBA', choices=['NBA', 'NCAAB', 'ALL'])
    parser.add_argument('--team', type=str, help='Show events for a specific team')
    parser.add_argument('--impact', action='store_true', help='Show all active team adjustments')
    parser.add_argument('--recent', type=int, help='Show events from last N days')
    args = parser.parse_args()

    tracker = RosterTracker()

    try:
        if args.update:
            result = tracker.update(args.sport)
            print(json.dumps(result, indent=2))

        elif args.team:
            events = tracker.get_team_events(args.team)
            adj = tracker.get_team_adjustment(args.team)
            print(f"\n{args.team} — Strength adjustment: {adj:+.4f}")
            print(f"Active events: {len(events)}")
            for ev in events:
                print(f"  [{ev['event_date']}] {ev['event_type']}: {ev['player'] or '—'} "
                      f"| impact={ev['impact_score']:+.4f} | {ev['description'][:60]}")

        elif args.impact:
            adjustments = tracker.compute_team_adjustments(args.sport)
            print(f"\nTeam Strength Adjustments ({args.sport}):")
            for team, adj in sorted(adjustments.items(), key=lambda x: x[1]):
                emoji = "🔴" if adj < -0.05 else ("🟢" if adj > 0.02 else "⚪")
                print(f"  {emoji} {team:<30} {adj:+.4f}")

        elif args.recent:
            c = tracker.conn.cursor()
            cutoff = (date.today() - timedelta(days=args.recent)).isoformat()
            rows = c.execute("""
                SELECT * FROM roster_events WHERE event_date >= ?
                ORDER BY event_date DESC, team
            """, (cutoff,)).fetchall()
            print(f"\nRoster events (last {args.recent} days): {len(rows)}")
            for r in rows:
                print(f"  [{r['event_date']}] {r['sport']} {r['team']:<25} "
                      f"{r['event_type']:<20} {r['player'] or '—':<20} "
                      f"impact={r['impact_score']:+.4f}")
        else:
            parser.print_help()

    finally:
        tracker.close()


if __name__ == '__main__':
    main()
