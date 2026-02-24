from result_tracker import load_picks_for_date
picks = load_picks_for_date('2026-02-20')
print(f'{len(picks)} picks loaded for 2026-02-20')
for p in picks:
    print(f"  {p['away']} @ {p['home']}: {p['pick']} ({p['win_prob']:.1%}) spread={p['spread']:+.1f} label={p['pick_label']}")
