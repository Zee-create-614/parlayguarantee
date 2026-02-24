# ParlayGuarantee Sports Data Engine

A Python-based parlay pick generator that uses real NBA data to create intelligent, diversified betting picks.

## 🏀 Features

- **Real Data Integration**: Fetches live NBA data using nba_api and The Odds API
- **Advanced Analysis**: Evaluates 15+ factors per game including:
  - Team records and recent form
  - Home/away performance
  - Injury reports and player impact
  - Travel fatigue and scheduling spots
  - Market line movement
- **Smart Parlay Generation**: Creates 10 diversified parlays (2-7 legs) with correlation avoidance
- **Results Tracking**: Automated verification and performance tracking
- **Extensible Architecture**: Designed for easy addition of NFL, MLB, NHL

## 📁 File Structure

```
engine/
├── requirements.txt      # Python dependencies
├── config.py            # API keys, constants, team data
├── data_fetcher.py      # API data collection
├── analyzer.py          # Game analysis engine
├── parlay_generator.py  # Parlay combination logic
├── result_checker.py    # Results verification
├── run_engine.py        # Main orchestrator
├── picks_output.json    # Generated picks (output)
├── engine.log           # Execution logs
└── history/             # Historical results
    ├── track_record.json
    └── results_YYYY-MM-DD.json
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set API Key (Optional)

For odds data, set your The Odds API key:

```bash
# Windows
set THE_ODDS_API_KEY=your_api_key_here

# Mac/Linux
export THE_ODDS_API_KEY=your_api_key_here
```

> The engine works without this key but won't have real-time odds

### 3. Run the Engine

```bash
python run_engine.py
```

This generates `picks_output.json` with 10 parlay picks for today's NBA games.

### 4. Check Results (Next Day)

```bash
python run_engine.py check picks_output.json 2026-02-15
```

## 📊 Output Format

The engine generates `picks_output.json` in this format:

```json
{
  "generated_at": "2026-02-15T21:00:00Z",
  "date": "2026-02-15",
  "sport": "NBA",
  "games_analyzed": 8,
  "parlays": [
    {
      "id": 1,
      "legs": 3,
      "type": "3-Leg Parlay",
      "combined_odds": "+580",
      "combined_decimal": 6.8,
      "confidence": 72,
      "picks": [
        {
          "game": "Lakers vs Celtics",
          "pick": "Celtics -4.5",
          "type": "spread",
          "odds": "-110",
          "reasoning": "Celtics 18-4 at home, Lakers on 2nd night of B2B"
        }
      ],
      "potential_payout": {
        "$10": "$68",
        "$25": "$170",
        "$50": "$340",
        "$100": "$680"
      }
    }
  ]
}
```

## 🔧 Configuration

Key settings in `config.py`:

- **PARLAY_CONFIG**: Number of parlays, leg counts, confidence ranges
- **ANALYSIS_WEIGHTS**: Factor importance in scoring algorithm
- **API_DELAYS**: Rate limiting between API calls
- **NBA_TEAM_COORDS**: Team locations for travel analysis

## 📈 Analysis Factors

### Team Performance (40%)
- Overall record and win percentage
- Home vs away splits
- Last 10 games form
- Offensive/defensive ratings

### Situational (35%)
- Rest days and back-to-back games
- Travel distance and timezone changes
- Head-to-head history
- Schedule spots and fatigue

### Injuries & Personnel (25%)
- Key player availability
- Impact of missing players
- Depth chart analysis

## 🎯 Parlay Strategy

### Diversification Rules
- **No Correlation**: Never combine spread + moneyline for same team
- **Game Spread**: Multiple games per parlay when possible
- **Bet Type Mix**: Spreads, moneylines, totals in each parlay
- **Confidence Levels**: Mix high-confidence + value plays

### Parlay Distribution
- **2-3 Legs**: High confidence, safer plays
- **4-5 Legs**: Balanced risk/reward
- **6-7 Legs**: Include value plays for bigger payouts

## 🏆 Performance Tracking

The engine automatically tracks:

- **Parlay Success Rate**: Percentage of winning parlays
- **Individual Pick Accuracy**: Win rate on single picks
- **Historical Performance**: Daily results over time
- **Confidence Calibration**: How well confidence correlates with results

Track record saved in `history/track_record.json`.

## 🔌 API Integration

### NBA Data (nba_api - Free)
- Today's games and schedules
- Team stats and ratings
- Player game logs
- Head-to-head history

### The Odds API (Free Tier: 500/month)
- Live spreads, moneylines, totals
- Multiple sportsbook consensus
- Line movement tracking
- Opening vs current lines

### Injury Data
- Current implementation is simplified
- Production version would integrate with:
  - ESPN API
  - NBA.com injury reports
  - RotoWire updates

## 🛠 Development

### Adding New Sports

1. Create sport-specific fetcher inheriting from `BaseSportFetcher`
2. Add sport constants to `config.py`
3. Extend analyzer for sport-specific factors
4. Update parlay generator for sport rules

### Custom Analysis Factors

Add new factors in `analyzer.py`:

```python
def analyze_custom_factor(self, team: str) -> float:
    # Your analysis logic
    return factor_score

# Update analyze_team_factors to include it
factors['custom_factor'] = self.analyze_custom_factor(team)
```

### Testing

```bash
# Test individual components
python data_fetcher.py
python analyzer.py
python parlay_generator.py
python result_checker.py

# Test with sample data
python run_engine.py test_output.json
```

## ⚠️ Important Notes

- **Rate Limits**: The engine respects API rate limits with built-in delays
- **Error Handling**: Gracefully handles API failures and missing data
- **No Fake Data**: Only uses real API data - no hardcoded predictions
- **Correlation Awareness**: Actively avoids correlated legs in parlays
- **Responsible Usage**: This is for educational/entertainment purposes

## 🆘 Troubleshooting

### Common Issues

**"No games found"**
- Check if today has NBA games scheduled
- Verify date format in API calls

**"API rate limit exceeded"**
- Increase delays in `API_DELAYS` config
- Consider upgrading to paid API tiers

**"Module not found"**
- Run `pip install -r requirements.txt`
- Check Python path configuration

**"Odds API error"**
- Verify THE_ODDS_API_KEY is set correctly
- Check API quota at theoddsapi.com

### Debug Mode

Enable detailed logging:

```python
# In run_engine.py
logging.basicConfig(level=logging.DEBUG)
```

## 📞 Support

For issues with:
- **NBA API**: Check nba_api documentation
- **The Odds API**: Visit theoddsapi.com
- **Engine Logic**: Review logs in `engine.log`

## 🚀 Deployment

The engine is designed to run daily via cron/scheduled task:

```bash
# Daily at 6 PM EST (after lineups announced)
0 18 * * * cd /path/to/engine && python run_engine.py
```

Output JSON can be consumed directly by web frontend.

---

**Built with ❤️ for ParlayGuarantee** | *Bet responsibly*