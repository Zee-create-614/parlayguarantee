import type { Metadata } from 'next'
import Link from 'next/link'
import Header from '../../components/Header'

export const metadata: Metadata = {
  title: 'How Our 37-Factor AI Betting Model Works | Parlay Guarantee',
  description: 'A deep dive into the AI and machine learning behind Parlay Guarantee. Learn how our 37-factor model analyzes NBA games to generate winning picks.',
  openGraph: {
    title: 'How Our 37-Factor AI Betting Model Works',
    description: 'Deep dive into the machine learning model behind Parlay Guarantee\'s sports picks.',
    type: 'article',
    url: 'https://parlayguarantee.com/blog/nba-betting-model',
  },
}

export default function NbaBettingModel() {
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: 'How Our 37-Factor AI Betting Model Works',
    description: 'A deep dive into the AI and machine learning behind Parlay Guarantee.',
    author: { '@type': 'Organization', name: 'Parlay Guarantee' },
    publisher: { '@type': 'Organization', name: 'Parlay Guarantee', url: 'https://parlayguarantee.com' },
    datePublished: '2026-02-10',
    dateModified: '2026-02-17',
    mainEntityOfPage: 'https://parlayguarantee.com/blog/nba-betting-model',
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
            <span className="text-text-muted text-sm">10 min read</span>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold mb-4">
            How Our <span className="text-accent-green">37-Factor</span> AI Betting Model Works
          </h1>
          <p className="text-text-muted text-lg">
            A transparent look under the hood at the machine learning system that powers every pick on Parlay Guarantee.
          </p>
        </header>

        <div className="prose prose-invert max-w-none space-y-6 text-text-primary/90 leading-relaxed">
          <p>
            &quot;AI-powered picks&quot; has become a buzzword in sports betting. Every tout and their cousin claims to have an algorithm. So what makes ours different? Transparency. We&apos;re going to walk you through exactly how our model works — from raw data to the pick that lands on your <Link href="/picks" className="text-accent-green hover:underline">picks page</Link>.
          </p>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">The 37 Factors: What We Analyze</h2>
          <p>
            Our model evaluates 37 distinct factors for every game. These fall into six categories:
          </p>

          <div className="space-y-6 my-8">
            {[
              {
                title: '1. Team Performance (8 factors)',
                color: 'accent-green',
                factors: [
                  'Offensive rating (points per 100 possessions)',
                  'Defensive rating (points allowed per 100)',
                  'Net rating (overall efficiency differential)',
                  'Pace (possessions per game)',
                  'Effective field goal percentage',
                  'Turnover rate',
                  'Offensive rebounding percentage',
                  'Free throw rate',
                ],
              },
              {
                title: '2. Player Impact (7 factors)',
                color: 'accent-gold',
                factors: [
                  'Weighted player efficiency ratings for active roster',
                  'Star player availability and minutes projection',
                  'Bench depth scoring (reserve unit net rating)',
                  'Key player usage rate and dependency',
                  'Injury report impact scoring (GTD, Out, Questionable)',
                  'Recent form — last 5 and last 10 game performance',
                  'Clutch performance metrics (last 5 minutes of close games)',
                ],
              },
              {
                title: '3. Matchup Dynamics (6 factors)',
                color: 'accent-green',
                factors: [
                  'Head-to-head record (last 3 seasons)',
                  'Style matchup scoring (pace differential, half-court vs transition)',
                  'Positional advantage mapping',
                  '3-point shooting vs perimeter defense',
                  'Paint scoring vs interior defense',
                  'Fast break efficiency differential',
                ],
              },
              {
                title: '4. Situational Factors (7 factors)',
                color: 'accent-gold',
                factors: [
                  'Home/away splits',
                  'Back-to-back game fatigue',
                  'Days of rest',
                  'Travel distance and time zones crossed',
                  'Altitude adjustment (Denver factor)',
                  'Rivalry and motivation scoring',
                  'Schedule spot (sandwich games, long road trips)',
                ],
              },
              {
                title: '5. Market Intelligence (5 factors)',
                color: 'accent-green',
                factors: [
                  'Opening line vs current line movement',
                  'Sharp money indicators (reverse line movement)',
                  'Public betting percentage',
                  'Steam moves and line freezes',
                  'Closing line value prediction',
                ],
              },
              {
                title: '6. Advanced & Historical (4 factors)',
                color: 'accent-gold',
                factors: [
                  'Referee assignment tendencies (foul rates, over/under lean)',
                  'Historical ATS performance in similar situations',
                  'Season trend momentum (last 20 games ATS)',
                  'Model consensus scoring (ensemble agreement)',
                ],
              },
            ].map((category) => (
              <div key={category.title} className={`bg-bg-secondary/60 border border-${category.color}/20 rounded-xl p-6`}>
                <h3 className={`text-lg font-bold text-${category.color} mb-3`}>{category.title}</h3>
                <ul className="space-y-1">
                  {category.factors.map((factor, i) => (
                    <li key={i} className="text-text-muted text-sm flex items-start gap-2">
                      <span className={`text-${category.color} mt-1`}>•</span>
                      {factor}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">The Model Architecture</h2>
          <p>
            We don&apos;t rely on a single algorithm. Our system uses an <strong>ensemble approach</strong> — multiple models that each analyze the data differently, then vote on the final prediction:
          </p>
          <ul className="list-disc pl-6 space-y-2 text-text-muted">
            <li><strong className="text-text-primary">Gradient Boosted Trees (XGBoost):</strong> Excellent at capturing non-linear relationships between factors. This is our workhorse for spread and total predictions.</li>
            <li><strong className="text-text-primary">Neural Network:</strong> A deep learning model that identifies complex patterns humans would never spot — like how a specific combination of rest days, travel, and opponent pace creates a predictable outcome.</li>
            <li><strong className="text-text-primary">Logistic Regression:</strong> A simpler, more interpretable model that serves as a sanity check. When all three models agree, our confidence is highest.</li>
            <li><strong className="text-text-primary">Bayesian Updating:</strong> As live data comes in (injury updates, line movements), our predictions update in real time using Bayesian probability.</li>
          </ul>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">From Data to Pick: The Pipeline</h2>
          <ol className="list-decimal pl-6 space-y-3 text-text-muted">
            <li><strong className="text-text-primary">Data Ingestion (6:00 AM ET):</strong> We pull the latest stats, injury reports, odds, and news from dozens of sources</li>
            <li><strong className="text-text-primary">Feature Engineering:</strong> Raw data is transformed into our 37 standardized factors for each game</li>
            <li><strong className="text-text-primary">Model Scoring:</strong> Each game is scored by all three models independently</li>
            <li><strong className="text-text-primary">Ensemble Voting:</strong> Models vote on each pick. We weight by recent accuracy.</li>
            <li><strong className="text-text-primary">Edge Calculation:</strong> The model&apos;s predicted probability is compared to implied odds from the betting market. Only games with a meaningful edge make the cut.</li>
            <li><strong className="text-text-primary">Pick Generation:</strong> Final picks are generated with confidence scores, recommended bet types, and detailed reasoning</li>
            <li><strong className="text-text-primary">Continuous Updates:</strong> Throughout the day, as new information arrives, picks are re-evaluated and updated</li>
          </ol>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">What &quot;Edge&quot; Actually Means</h2>
          <p>
            In sports betting, edge is the difference between the true probability of an outcome and what the odds imply. For example:
          </p>
          <div className="bg-bg-secondary/60 border border-accent-green/20 rounded-xl p-6 my-6">
            <p className="text-text-muted text-sm">
              If a team is listed at <strong className="text-text-primary">+150</strong> (implied probability: 40%), but our model calculates a <strong className="text-accent-green">48% true probability</strong>, that&apos;s an <strong className="text-accent-gold">8% edge</strong>. Over hundreds of bets, consistently finding 3-8% edges is what separates profitable bettors from the rest.
            </p>
          </div>
          <p>
            We only recommend picks where our model identifies a minimum edge threshold. No edge, no pick — even if we have a prediction on who wins.
          </p>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">Continuous Learning</h2>
          <p>
            Our model isn&apos;t static. After every game, results are fed back into the system. The model tracks its own performance across different bet types, situations, and confidence levels — and adjusts. This means the model that generates your picks tonight is smarter than the one from last month.
          </p>
          <p>
            We also run regular backtests against historical seasons to validate that improvements hold up across different market conditions, not just recent trends.
          </p>

          <h2 className="text-2xl font-bold text-text-primary mt-10 mb-4">See It in Action</h2>
          <p>
            Theory is great, but results matter. Check out <Link href="/blog/nba-picks-today" className="text-accent-green hover:underline">today&apos;s NBA picks</Link> to see the model&apos;s output, or visit the <Link href="/picks" className="text-accent-green hover:underline">picks page</Link> to view our tracked history. For the full experience with confidence scores and detailed analysis, <Link href="/auth/signin" className="text-accent-green hover:underline">create a free account</Link>.
          </p>
        </div>

        {/* CTA */}
        <div className="mt-14 bg-gradient-to-r from-accent-green/10 to-accent-gold/10 border border-accent-green/30 rounded-2xl p-8 text-center">
          <h2 className="text-2xl font-bold mb-3">Experience the Model Yourself</h2>
          <p className="text-text-muted mb-6">37 factors. 3 models. One edge. See it in action.</p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/picks" className="bg-accent-green text-bg-primary font-bold px-8 py-3 rounded-lg hover:bg-accent-green/90 transition-colors">
              View Today&apos;s Picks →
            </Link>
            <Link href="/pricing" className="border border-accent-gold text-accent-gold font-bold px-8 py-3 rounded-lg hover:bg-accent-gold/10 transition-colors">
              View Premium Plans
            </Link>
          </div>
        </div>
      </article>
    </>
  )
}
