from reliable_data_fetcher import ReliableDataFetcher
f = ReliableDataFetcher()
stats = f.fetch_team_stats()
print(f'Teams: {len(stats)}')
for team in sorted(stats.keys()):
    s = stats[team]
    print(f"  {team:<28} {s['wins']:>2}-{s['losses']:>2} ({s['win_pct']:.3f}) PPG={s['ppg']:>5} PAPG={s['papg']:>5} Streak={s['streak']:>3} Home={s['home_record']} Road={s['road_record']} L10={s['last_ten']}")
