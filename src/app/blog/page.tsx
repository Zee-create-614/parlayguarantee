import type { Metadata } from 'next'
import Link from 'next/link'
import Header from '../components/Header'

export const metadata: Metadata = {
  title: 'Sports Betting Blog | Expert Picks, Strategies & AI Insights | Parlay Guarantee',
  description: 'Expert sports betting articles, NBA picks, parlay strategies, and AI betting model insights. Free tips and analysis from Parlay Guarantee.',
  openGraph: {
    title: 'Sports Betting Blog | Parlay Guarantee',
    description: 'Expert picks, parlay strategies, and AI betting insights updated daily.',
    type: 'website',
    url: 'https://parlayguarantee.com/blog',
  },
}

const posts = [
  {
    slug: 'nba-picks-today',
    title: 'NBA Picks Today — AI-Powered Predictions',
    excerpt: 'Get today\'s top NBA picks powered by our 37-factor AI model. Updated daily with spread, moneyline, and over/under predictions.',
    category: 'Daily Picks',
    date: '2026-02-17',
    readTime: '5 min',
    emoji: '🏀',
  },
  {
    slug: 'best-parlays-tonight',
    title: 'Best Parlay Picks Tonight',
    excerpt: 'Tonight\'s highest-confidence parlay combinations across NBA, NHL, and more. Curated by AI for maximum edge.',
    category: 'Daily Picks',
    date: '2026-02-17',
    readTime: '6 min',
    emoji: '🎯',
  },
  {
    slug: 'free-sports-picks',
    title: 'Free Sports Picks & Predictions',
    excerpt: 'Access free AI-generated sports picks daily. See why thousands of bettors trust our model before upgrading to premium.',
    category: 'Free Picks',
    date: '2026-02-15',
    readTime: '7 min',
    emoji: '🆓',
  },
  {
    slug: 'march-madness-picks-2026',
    title: 'March Madness Picks 2026 — AI Bracket Predictions',
    excerpt: 'Our AI model is ready for the 2026 NCAA Tournament. Early bracket predictions, Cinderella picks, and upset alerts.',
    category: 'March Madness',
    date: '2026-02-14',
    readTime: '8 min',
    emoji: '🏆',
  },
  {
    slug: 'nba-betting-model',
    title: 'How Our 37-Factor AI Betting Model Works',
    excerpt: 'A deep dive into the machine learning model behind Parlay Guarantee — from data ingestion to pick generation.',
    category: 'Education',
    date: '2026-02-10',
    readTime: '10 min',
    emoji: '🤖',
  },
  {
    slug: 'parlay-strategy-guide',
    title: 'Parlay Betting Strategy Guide',
    excerpt: 'Everything you need to know about parlay betting — bankroll management, leg selection, correlation strategies, and more.',
    category: 'Education',
    date: '2026-02-08',
    readTime: '12 min',
    emoji: '📚',
  },
]

export default function BlogIndex() {
  return (
    <>
      <Header />
      <main className="max-w-6xl mx-auto px-4 pt-24 pb-32">
        <div className="text-center mb-16">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">
            Sports Betting <span className="text-accent-green">Blog</span>
          </h1>
          <p className="text-text-muted text-lg max-w-2xl mx-auto">
            Expert picks, AI insights, and betting strategies to sharpen your edge. Updated daily.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {posts.map((post) => (
            <Link
              key={post.slug}
              href={`/blog/${post.slug}`}
              className="group bg-bg-secondary/60 border border-accent-green/10 rounded-xl p-6 hover:border-accent-green/40 transition-all duration-300 hover:-translate-y-1"
            >
              <div className="flex items-center gap-2 mb-3">
                <span className="text-2xl">{post.emoji}</span>
                <span className="text-xs font-medium text-accent-green bg-accent-green/10 px-2 py-1 rounded-full">
                  {post.category}
                </span>
              </div>
              <h2 className="text-xl font-bold mb-2 group-hover:text-accent-green transition-colors">
                {post.title}
              </h2>
              <p className="text-text-muted text-sm mb-4">{post.excerpt}</p>
              <div className="flex items-center justify-between text-xs text-text-muted">
                <span>{post.date}</span>
                <span>{post.readTime} read</span>
              </div>
            </Link>
          ))}
        </div>

        {/* CTA */}
        <div className="mt-16 text-center bg-bg-secondary/60 border border-accent-green/20 rounded-2xl p-10">
          <h2 className="text-2xl font-bold mb-3">Want AI Picks Delivered Daily?</h2>
          <p className="text-text-muted mb-6 max-w-lg mx-auto">
            Stop reading about picks — start getting them. Our AI model analyzes 37 factors per game to find your edge.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/auth/signin"
              className="bg-accent-green text-bg-primary font-bold px-8 py-3 rounded-lg hover:bg-accent-green/90 transition-colors"
            >
              Get Free Picks →
            </Link>
            <Link
              href="/pricing"
              className="border border-accent-gold text-accent-gold font-bold px-8 py-3 rounded-lg hover:bg-accent-gold/10 transition-colors"
            >
              View Premium Plans
            </Link>
          </div>
        </div>
      </main>
    </>
  )
}
