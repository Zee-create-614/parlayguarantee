import sqlite3
conn = sqlite3.connect('results.db')
cur = conn.cursor()

print("=" * 60)
print("PARLAYGUARANTEE P&L REPORT")
print("=" * 60)

# All daily summaries
rows = cur.execute("SELECT date, product, total_picks, correct_picks, accuracy, spread_correct, spread_total, spread_accuracy, ou_correct, ou_total, ou_accuracy, deposit_kept FROM daily_summaries ORDER BY date, product").fetchall()

# Group by date
from collections import defaultdict
by_date = defaultdict(list)
for r in rows:
    by_date[r[0]].append(r)

for date in sorted(by_date.keys()):
    print(f"\n[{date}]")
    for r in by_date[date]:
        product = r[1]
        if 'ou' in product:
            print(f"  {product}: O/U {r[8]}/{r[9]} ({r[10]:.1f}%)")
        else:
            print(f"  {product}: Straight {r[3]}/{r[2]} ({r[4]:.1f}%) | Spread {r[5]}/{r[6]} ({r[7]:.1f}%) | Deposit: {'KEPT' if r[11] else 'LOST'}")

# Totals
print("\n" + "=" * 60)
print("CUMULATIVE TOTALS")
print("=" * 60)

# NBA straight
nba = cur.execute("SELECT SUM(total_picks), SUM(correct_picks), SUM(spread_correct), SUM(spread_total) FROM daily_summaries WHERE product='nba_engine'").fetchone()
print(f"\nNBA Straight: {nba[1]}/{nba[0]} ({nba[1]/nba[0]*100:.1f}%)" if nba[0] else "")
print(f"NBA Spread:   {nba[2]}/{nba[3]} ({nba[2]/nba[3]*100:.1f}%)" if nba[3] else "")

# NBA O/U
nba_ou = cur.execute("SELECT SUM(ou_correct), SUM(ou_total) FROM daily_summaries WHERE product='nba_ou'").fetchone()
if nba_ou[1]: print(f"NBA O/U:      {nba_ou[0]}/{nba_ou[1]} ({nba_ou[0]/nba_ou[1]*100:.1f}%)")

# NCAAB straight
ncaab = cur.execute("SELECT SUM(total_picks), SUM(correct_picks), SUM(spread_correct), SUM(spread_total) FROM daily_summaries WHERE product='ncaab_engine'").fetchone()
if ncaab[0]: print(f"\nNCAAB Straight: {ncaab[1]}/{ncaab[0]} ({ncaab[1]/ncaab[0]*100:.1f}%)")
if ncaab[3]: print(f"NCAAB Spread:   {ncaab[2]}/{ncaab[3]} ({ncaab[2]/ncaab[3]*100:.1f}%)")

# NCAAB O/U
ncaab_ou = cur.execute("SELECT SUM(ou_correct), SUM(ou_total) FROM daily_summaries WHERE product='ncaab_ou'").fetchone()
if ncaab_ou[1]: print(f"NCAAB O/U:      {ncaab_ou[0]}/{ncaab_ou[1]} ({ncaab_ou[0]/ncaab_ou[1]*100:.1f}%)")

# Deposit tracking
deposits = cur.execute("SELECT COUNT(*), SUM(deposit_kept) FROM daily_summaries WHERE product='nba_engine'").fetchone()
print(f"\nNBA Deposit Record: {deposits[1]}/{deposits[0]} kept ({deposits[1]/deposits[0]*100:.0f}%)" if deposits[0] else "")

# Hypothetical P&L assuming $100 flat bets at -110
print("\n" + "=" * 60)
print("HYPOTHETICAL P&L ($100 flat bets at -110)")
print("=" * 60)

# Get all spread results
all_spread = cur.execute("SELECT date, spread_pick, spread_correct FROM pick_results WHERE spread_correct IS NOT NULL").fetchall()
wins = sum(1 for r in all_spread if r[2] == 1)
losses = len(all_spread) - wins
profit = wins * 90.91 - losses * 100  # -110 odds
print(f"Spread bets: {wins}W-{losses}L")
print(f"P&L: ${profit:+,.2f}")
print(f"ROI: {profit / (len(all_spread) * 100) * 100:+.1f}%")

# O/U results
all_ou = cur.execute("SELECT date, ou_pick, ou_correct FROM pick_results WHERE ou_correct IS NOT NULL").fetchall()
ou_wins = sum(1 for r in all_ou if r[2] == 1)
ou_losses = len(all_ou) - ou_wins
ou_profit = ou_wins * 90.91 - ou_losses * 100
print(f"\nO/U bets: {ou_wins}W-{ou_losses}L")
print(f"P&L: ${ou_profit:+,.2f}")
print(f"ROI: {ou_profit / (len(all_ou) * 100) * 100:+.1f}%")

combined = profit + ou_profit
total_bets = len(all_spread) + len(all_ou)
print(f"\nCOMBINED P&L: ${combined:+,.2f} on {total_bets} bets")
print(f"COMBINED ROI: {combined / (total_bets * 100) * 100:+.1f}%")

conn.close()
