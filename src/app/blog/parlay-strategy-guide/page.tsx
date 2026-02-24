import type { Metadata } from 'next'
import Link from 'next/link'
import Header from '../../components/Header'

export const metadata: Metadata = {
  title: 'Parlay Betting Strategy Guide — Win More Parlays | Parlay Guarantee',
  description: 'Complete parlay betting strategy guide. Learn bankroll management, leg selection, correlation strategies, and how to build profitable parlays consistently.',
  openGraph: {
    title: 'Parlay Betting Strategy Guide',
    description: 'Complete guide to profitable parlay betting — bankroll management, correlation strategies, and more.',
    type: 'article',
    url: 'https://parlayguarantee.com/blog/parlay-strategy-guide',
  },
}

export default function ParlayStrategyGuide() {
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: 'Parlay Betting Strategy Guide — Win More Parlays',
    description: 'Complete parlay betting strategy guide covering bankroll management, leg selection, and correlation strategies.',
    author: { '@type': 'Organization', name: 'Parlay Guarantee' },
    publisher: { '@type': 'Organization', name: 'Parlay Guarantee', url: 'https://parlayguarantee.com' },
    datePublished: '2026-02-08',
    dateModified: '2026-02-17',
    mainEntityOfPage: 'https://parlayguarantee.com/blog/parlay-strategy-guide',
  }

  return (
    <>
      <Header />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <article className="max-w-4xl mx-auto px-4 pt-24 pb-32">
        <div className="mb-8">
          <Link href="/blog" className="text-accent-green text-sm hover:underline">← Back to Blog</Link>
        </div>
        <header className="mb-10">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-accent-green bg-accent-green/10 text-xs font-medium px-3 py-1 rounded-full">Education</span>
            <span className="text-text-muted text-sm">12 min read</span>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold mb-4">
            Parlay Betting <span className="text-accent-green">Strategy Guide</span>
          </h1>
          <p className="text-text-muted text-lg">
            Everything you need to know about building profitable parlays — from bankroll management to correlation strategies used by sharp bettors.
          </p>
        </header>

        <div className="prose prose-invert max-w-none space-y-6 text-text-primary/90 leading-relaxed">
          <p>
            Parlays are the most popular — and most misunderstood — bet type in sports betting. The allure is obvious: turn a small stake into a massive payout by combining multiple bets into one. But most bettors approach parlays like lottery tickets, and their bankrolls suffer for it.
          </p>
          <p>
            This guide will teach you how sharp bettors and our <Link href="/blog/nba-betting-model" className="text-accent-green hover:underline">AI model</Link> approach parlay betting — strategically, mathematically, and profitably.
          </p>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">What Is a Parlay?</h2>
          <p>
            A parlay (also called an accumulator or multi-bet) combines two or more individual bets into a single wager. All legs must win for the parlay to pay out. The payout is calculated by multiplying the odds of each leg together, creating significantly higher potential returns than betting each game individually.
          </p>
          <div className="bg-bg-secondary/60 border border-accent-green/20 rounded-xl p-6 my-6">
            <h3 className="font-bold text-accent-green mb-2">Example: 3-Leg Parlay</h3>
            <div className="space-y-2 text-text-muted text-sm">
              <p>Leg 1: Lakers -3.5 (-110) → implied prob ~52%</p>
              <p>Leg 2: Celtics ML (-150) → implied prob ~60%</p>
              <p>Leg 3: Warriors/Kings Over 228 (-110) → implied prob ~52%</p>
              <p className="text-accent-gold font-bold pt-2">Combined odds: approximately +500 (6x payout)</p>
              <p className="text-text-primary">$50 bet → $300 potential payout</p>
              <p className="text-text-muted">Win probability: ~16% (assuming independent outcomes)</p>
            </div>
          </div>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">The Math: Why Most Parlays Lose (And How to Beat It)</h2>
          <p>
            Let&apos;s be honest about the math. Sportsbooks love parlays because the house edge compounds with each leg. On a standard 2-leg parlay at -110/-110, the true fair payout should be +300, but books typically pay +264. That gap grows with each leg.
          </p>
          <p>
            So how do you overcome this? Two ways:
          </p>
          <ol className="list-decimal pl-6 space-y-3 text-text-muted">
            <li><strong className="text-text-primary">Only include legs with positive expected value.</strong> If every individual leg has an edge, the parlay mathematically has an edge too (minus the vig penalty). This is what our AI does — it only combines legs where the model has identified mispriced odds.</li>
            <li><strong className="text-text-primary">Use correlated parlays.</strong> When outcomes are positively correlated, the true probability of the parlay hitting is higher than what independent odds suggest. Sportsbooks are getting better at pricing these, but inefficiencies remain — especially in same-game parlays.</li>
          </ol>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Correlation: The Secret Weapon</h2>
          <p>
            Correlation is the single most important concept in parlay betting. Two events are correlated when one happening makes the other more likely. Examples:
          </p>
          <div className="grid md:grid-cols-2 gap-4 my-6">
            {[
              { title: '✅ Positive Correlation', examples: ['Team wins + star player over on points', 'Game over + underdog covers (high-scoring games favor underdogs)', 'First half over + full game over', 'Quarterback over on passing yards + team wins'] },
              { title: '❌ Negative Correlation', examples: ['Both teams to cover (impossible by definition)', 'Game under + high-scoring player props', 'Blowout winner + game goes to OT'] },
            ].map((type) => (
              <div key={type.title} className="bg-bg-secondary/60 border border-accent-green/10 rounded-lg p-4">
                <h3 className="font-bold mb-2">{type.title}</h3>
                <ul className="space-y-1">
                  {type.examples.map((ex, i) => (
                    <li key={i} className="text-text-muted text-sm">• {ex}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p>
            When you build a parlay with positively correlated legs, you&apos;re getting paid as if the events are independent, but they&apos;re actually more likely to hit together. This is where real edge lives.
          </p>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Optimal Parlay Size: The Data</h2>
          <p>
            How many legs should your parlay have? Here&apos;s what the math says:
          </p>
          <div className="bg-bg-secondary/60 border border-accent-green/20 rounded-xl p-6 my-6">
            <div className="space-y-3">
              {[
                { legs: '2 legs', rate: '~25-30%', edge: 'Lowest vig penalty, most consistent. Best for serious bankroll growth.', rec: 'Recommended' },
                { legs: '3 legs', rate: '~12-18%', edge: 'Sweet spot of payout vs probability. Our most popular tier.', rec: 'Recommended' },
                { legs: '4 legs', rate: '~6-10%', edge: 'Meaningful payouts but requires strong conviction on all legs.', rec: 'Occasional' },
                { legs: '5+ legs', rate: '<5%', edge: 'House edge becomes enormous. Fun money only.', rec: 'Entertainment only' },
              ].map((item) => (
                <div key={item.legs} className="flex flex-col md:flex-row md:items-center gap-2 md:gap-4 text-sm">
                  <span className="font-bold text-text-primary w-20">{item.legs}</span>
                  <span className="text-accent-green w-24">Hit rate: {item.rate}</span>
                  <span className="text-text-muted flex-1">{item.edge}</span>
                  <span className={`text-xs px-2 py-1 rounded-full ${item.rec === 'Recommended' ? 'bg-accent-green/10 text-accent-green' : item.rec === 'Occasional' ? 'bg-accent-gold/10 text-accent-gold' : 'bg-loss-red/10 text-loss-red'}`}>
                    {item.rec}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Bankroll Management for Parlay Bettors</h2>
          <p>
            This is where most parlay bettors blow up. You hit a big parlay, feel invincible, size up your next bet, and lose it all in a week. Here&apos;s the disciplined approach:
          </p>
          <ul className="list-disc pl-6 space-y-3 text-text-muted">
            <li><strong className="text-text-primary">Set a parlay bankroll.</strong> This should be a subset of your total sports betting bankroll — maybe 20-30%. The rest goes to straight bets.</li>
            <li><strong className="text-text-primary">Size by legs.</strong> 2-leg parlays: 2-3% of parlay bankroll. 3-leg: 1-2%. 4-leg: 0.5-1%. This ensures no single loss is catastrophic.</li>
            <li><strong className="text-text-primary">Never chase.</strong> Lost a parlay by one leg? It happens constantly. Do not increase your next bet size to &quot;make it back.&quot; Stick to the system.</li>
            <li><strong className="text-text-primary">Track everything.</strong> Log every parlay — legs, odds, stake, result. After 100 parlays, analyze your results by leg count, sport, and bet type. Data beats feelings.</li>
            <li><strong className="text-text-primary">Take profits.</strong> When your parlay bankroll grows 50%+, withdraw some profits. This locks in gains and resets your risk exposure.</li>
          </ul>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Common Parlay Strategies</h2>
          <div className="space-y-4 my-6">
            {[
              { title: '🎯 The Correlated SGP', desc: 'Build same-game parlays with logically connected outcomes. Example: Team A to win + Team A over team total + Star Player over on points. If the team wins big, all three legs likely hit.' },
              { title: '🔄 The Round Robin', desc: 'Instead of one 4-leg parlay, create multiple 2-leg and 3-leg combinations from your 4 picks. You won\'t need all 4 to hit to profit, reducing variance significantly.' },
              { title: '💰 The Value Hunter', desc: 'Only parlay legs where your model (or our AI) identifies +EV. No filler legs to "boost the payout." Two strong picks beat four mediocre ones.' },
              { title: '🛡️ The Hedge Play', desc: 'When your parlay is alive with one leg remaining, consider hedging by betting the other side of the final game. You lock in profit regardless of outcome.' },
            ].map((strat) => (
              <div key={strat.title} className="bg-bg-secondary/60 border border-accent-green/10 rounded-lg p-5">
                <h3 className="text-lg font-bold mb-2">{strat.title}</h3>
                <p className="text-text-muted text-sm">{strat.desc}</p>
              </div>
            ))}
          </div>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Mistakes That Kill Parlay Bankrolls</h2>
          <ol className="list-decimal pl-6 space-y-2 text-text-muted">
            <li><strong className="text-text-primary">Stacking favorites.</strong> Five -200 favorites in a parlay sounds safe but only hits ~13% of the time with a mediocre payout. The juice kills you.</li>
            <li><strong className="text-text-primary">Random sport mixing.</strong> NBA spread + NFL total + MLB moneyline with zero correlation is just gambling with extra steps.</li>
            <li><strong className="text-text-primary">Too many legs.</strong> Every leg multiplies your risk. The 10-leg parlay screenshots on Twitter are survivorship bias — you don&apos;t see the 10,000 that missed.</li>
            <li><strong className="text-text-primary">Emotional picks.</strong> Your favorite team shouldn&apos;t be in every parlay. Bias is the enemy of edge.</li>
            <li><strong className="text-text-primary">No tracking.</strong> If you don&apos;t know your actual win rate by leg count and sport, you&apos;re flying blind.</li>
          </ol>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Let AI Build Your Parlays</h2>
          <p>
            Everything in this guide — correlation analysis, edge calculation, optimal sizing — is what our AI model does automatically, thousands of times per night. Instead of spending hours researching and second-guessing, you can see <Link href="/blog/best-parlays-tonight" className="text-accent-green hover:underline">tonight&apos;s AI-curated parlays</Link> ready to go.
          </p>
          <p>
            <Link href="/auth/signin" className="text-accent-green hover:underline">Start with a free account</Link> to see the model in action, or check out <Link href="/pricing" className="text-accent-green hover:underline">premium plans</Link> for the full suite of picks, confidence scores, and parlay recommendations.
          </p>
        </div>

        {/* CTA */}
        <div className="mt-14 bg-gradient-to-r from-accent-green/10 to-accent-gold/10 border border-accent-green/30 rounded-2xl p-8 text-center">
          <h2 className="text-2xl font-bold mb-3">Ready to Build Smarter Parlays?</h2>
          <p className="text-text-muted mb-6">Let our AI handle the correlation math. You handle the celebration.</p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/auth/signin" className="bg-accent-green text-bg-primary font-bold px-8 py-3 rounded-lg hover:bg-accent-green/90 transition-colors">
              Get Free Picks →
            </Link>
            <Link href="/picks" className="border border-white/20 text-white font-bold px-8 py-3 rounded-lg hover:bg-white/5 transition-colors">
              View Tonight&apos;s Parlays
            </Link>
          </div>
        </div>
      </article>
    </>
  )
}
