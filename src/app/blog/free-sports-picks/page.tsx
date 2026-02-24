import type { Metadata } from 'next'
import Link from 'next/link'
import Header from '../../components/Header'

export const metadata: Metadata = {
  title: 'Free Sports Picks & Predictions — Daily AI Picks | Parlay Guarantee',
  description: 'Get free AI-powered sports picks daily. NBA, NFL, MLB, NHL predictions from our 37-factor model. No credit card required.',
  openGraph: {
    title: 'Free Sports Picks & Predictions',
    description: 'Free AI-powered sports picks updated daily. No credit card required.',
    type: 'article',
    url: 'https://parlayguarantee.com/blog/free-sports-picks',
  },
}

export default function FreeSportsPicks() {
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: 'Free Sports Picks & Predictions — Daily AI Picks',
    description: 'Get free AI-powered sports picks daily from our 37-factor model.',
    author: { '@type': 'Organization', name: 'Parlay Guarantee' },
    publisher: { '@type': 'Organization', name: 'Parlay Guarantee', url: 'https://parlayguarantee.com' },
    datePublished: '2026-02-15',
    dateModified: '2026-02-17',
    mainEntityOfPage: 'https://parlayguarantee.com/blog/free-sports-picks',
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
            <span className="text-accent-green bg-accent-green/10 text-xs font-medium px-3 py-1 rounded-full">Free Picks</span>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold mb-4">
            Free Sports Picks & <span className="text-accent-green">Predictions</span>
          </h1>
          <p className="text-text-muted text-lg">
            Access AI-generated sports picks at zero cost. See our model in action before committing a dime.
          </p>
        </header>

        <div className="prose prose-invert max-w-none space-y-6 text-text-primary/90 leading-relaxed">
          <p>
            Everyone promises free sports picks, but most &quot;free&quot; picks are just bait — vague predictions with no accountability, designed to upsell you on overpriced packages. At <strong>Parlay Guarantee</strong>, we do things differently. Our free picks come from the exact same <Link href="/blog/nba-betting-model" className="text-accent-green hover:underline">37-factor AI model</Link> that powers our premium tier. Same algorithm, same data, same methodology.
          </p>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">What You Get for Free</h2>
          <p>
            When you <Link href="/auth/signin" className="text-accent-green hover:underline">create a free account</Link>, you immediately unlock:
          </p>
          <ul className="list-disc pl-6 space-y-2 text-text-muted">
            <li><strong className="text-text-primary">Daily Featured Picks:</strong> 1-3 of our highest-confidence picks from tonight&apos;s slate, completely free</li>
            <li><strong className="text-text-primary">Pick History & Results:</strong> Full transparency into past performance — wins, losses, and overall record</li>
            <li><strong className="text-text-primary">Basic Game Analysis:</strong> Key factors our model identified for each featured matchup</li>
            <li><strong className="text-text-primary">Community Access:</strong> Join thousands of bettors using data-driven picks</li>
          </ul>

          <div className="bg-bg-secondary/60 border border-accent-gold/20 rounded-xl p-6 my-8">
            <h3 className="text-xl font-bold text-accent-gold mb-2">Why Do We Give Picks Away?</h3>
            <p className="text-text-muted">
              Simple: we want you to see the quality before you buy. Most sports pick services hide behind paywalls because they can&apos;t afford scrutiny. We give you free access because our model speaks for itself. When you see it winning consistently, upgrading to premium becomes a no-brainer.
            </p>
          </div>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Free vs. Premium: What&apos;s the Difference?</h2>
          <div className="overflow-x-auto my-6">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-accent-green/20">
                  <th className="py-3 pr-4 text-text-primary">Feature</th>
                  <th className="py-3 px-4 text-accent-green">Free</th>
                  <th className="py-3 px-4 text-accent-gold">Premium</th>
                </tr>
              </thead>
              <tbody className="text-text-muted">
                <tr className="border-b border-white/5">
                  <td className="py-3 pr-4">Daily picks</td>
                  <td className="py-3 px-4">1-3 featured</td>
                  <td className="py-3 px-4">Full slate (all games)</td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="py-3 pr-4">Confidence scores</td>
                  <td className="py-3 px-4">—</td>
                  <td className="py-3 px-4">✅ Detailed ratings</td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="py-3 pr-4">Parlay builder</td>
                  <td className="py-3 px-4">—</td>
                  <td className="py-3 px-4">✅ AI-optimized combos</td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="py-3 pr-4">Player props</td>
                  <td className="py-3 px-4">—</td>
                  <td className="py-3 px-4">✅ Full analysis</td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="py-3 pr-4">Real-time updates</td>
                  <td className="py-3 px-4">End of day</td>
                  <td className="py-3 px-4">✅ Live updates</td>
                </tr>
                <tr>
                  <td className="py-3 pr-4">Money-back guarantee</td>
                  <td className="py-3 px-4">—</td>
                  <td className="py-3 px-4">✅ Full refund protection</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Sports We Cover</h2>
          <p>
            Our AI model is built sport-by-sport, with specialized factors for each league:
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 my-6">
            {[
              { emoji: '🏀', name: 'NBA', status: 'Live' },
              { emoji: '🏈', name: 'NFL', status: 'Coming Soon' },
              { emoji: '⚾', name: 'MLB', status: 'Coming Soon' },
              { emoji: '🏒', name: 'NHL', status: 'Coming Soon' },
              { emoji: '🥊', name: 'UFC/MMA', status: 'Coming Soon' },
              { emoji: '⚽', name: 'Soccer', status: 'Coming Soon' },
              { emoji: '🏀', name: 'NCAAB', status: 'Coming Soon' },
              { emoji: '🏈', name: 'NCAAF', status: 'Coming Soon' },
            ].map((sport) => (
              <div key={sport.name} className="bg-bg-secondary/60 border border-accent-green/10 rounded-lg p-3 text-center">
                <span className="text-2xl">{sport.emoji}</span>
                <p className="font-bold text-sm mt-1">{sport.name}</p>
                <p className={`text-xs ${sport.status === 'Live' ? 'text-accent-green' : 'text-text-muted'}`}>{sport.status}</p>
              </div>
            ))}
          </div>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">How to Make the Most of Free Picks</h2>
          <p>
            Getting free picks is just the start. Here&apos;s how to use them wisely:
          </p>
          <ol className="list-decimal pl-6 space-y-3 text-text-muted">
            <li><strong className="text-text-primary">Track your results:</strong> Don&apos;t just tail blindly. Keep a spreadsheet of every pick you follow — bet type, odds, stake, and result. After 30 days, you&apos;ll have real data on whether the model works for you.</li>
            <li><strong className="text-text-primary">Start with flat betting:</strong> Bet the same amount on every pick while you&apos;re evaluating. This removes bet-sizing bias from your analysis.</li>
            <li><strong className="text-text-primary">Read the analysis:</strong> Don&apos;t just follow the pick — understand <em>why</em> the model likes it. This helps you spot when external factors (breaking news, weather) might invalidate a pick.</li>
            <li><strong className="text-text-primary">Be patient:</strong> Any model needs 50-100+ picks to show its edge. Don&apos;t judge after 5 games. Variance is real, and even a 55% model will have losing weeks.</li>
            <li><strong className="text-text-primary">Combine with your own research:</strong> Our AI provides the data backbone. If you have additional context (you watch every Celtics game, for example), layering your knowledge on top of our data is a powerful combo.</li>
          </ol>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Why &quot;Free Picks&quot; Sites Are Usually Scams</h2>
          <p>
            Let&apos;s be honest: most free pick sites are garbage. Here&apos;s what to watch out for:
          </p>
          <ul className="list-disc pl-6 space-y-2 text-text-muted">
            <li><strong className="text-text-primary">No tracked record:</strong> If a site doesn&apos;t show verified past results, they&apos;re hiding something</li>
            <li><strong className="text-text-primary">Vague picks:</strong> &quot;I like the Lakers tonight&quot; isn&apos;t a pick. A real pick has a specific line, odds, and stake recommendation</li>
            <li><strong className="text-text-primary">Guaranteed winners:</strong> No one wins 100% of the time. If they claim to, run</li>
            <li><strong className="text-text-primary">Pressure tactics:</strong> &quot;This pick expires in 10 minutes!&quot; is a sales tactic, not sports analysis</li>
          </ul>
          <p>
            At Parlay Guarantee, every pick — free and premium — is logged, timestamped, and publicly trackable. We earn trust through transparency.
          </p>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Get Started in 30 Seconds</h2>
          <p>
            No credit card. No commitment. Just <Link href="/auth/signin" className="text-accent-green hover:underline">create your free account</Link>, and you&apos;ll see today&apos;s picks immediately. If you like what you see, <Link href="/pricing" className="text-accent-green hover:underline">premium plans</Link> start at just a few dollars per day — with a full money-back guarantee.
          </p>
        </div>

        {/* CTA */}
        <div className="mt-14 bg-gradient-to-r from-accent-green/10 to-accent-gold/10 border border-accent-green/30 rounded-2xl p-8 text-center">
          <h2 className="text-2xl font-bold mb-3">Start Getting Free Picks Today</h2>
          <p className="text-text-muted mb-6">No credit card required. See our AI in action.</p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/auth/signin" className="bg-accent-green text-bg-primary font-bold px-8 py-3 rounded-lg hover:bg-accent-green/90 transition-colors">
              Create Free Account →
            </Link>
            <Link href="/picks" className="border border-white/20 text-white font-bold px-8 py-3 rounded-lg hover:bg-white/5 transition-colors">
              View Today&apos;s Picks
            </Link>
          </div>
        </div>
      </article>
    </>
  )
}
