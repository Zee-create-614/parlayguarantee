'use client'

import { useState, useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'

function LandingPageContent() {
  const [email, setEmail] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  
  const searchParams = useSearchParams()
  const utmSource = searchParams?.get('utm_source') || ''
  const utmMedium = searchParams?.get('utm_medium') || ''
  const utmCampaign = searchParams?.get('utm_campaign') || ''

  // Track page view with UTM parameters
  useEffect(() => {
    if (typeof window !== 'undefined' && window.gtag) {
      window.gtag('event', 'page_view', {
        page_title: 'AI Sports Picks Landing Page',
        page_location: window.location.href,
        utm_source: utmSource,
        utm_medium: utmMedium,
        utm_campaign: utmCampaign,
      })
    }
  }, [utmSource, utmMedium, utmCampaign])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || isSubmitting) return

    setIsSubmitting(true)

    try {
      // Track conversion
      if (typeof window !== 'undefined' && window.gtag) {
        window.gtag('event', 'conversion', {
          send_to: 'AW-CONVERSION_ID/CONVERSION_LABEL', // Replace with actual conversion tracking
          value: 1.0,
          currency: 'USD',
          transaction_id: '',
        })
      }

      // Build sign-up URL with UTM parameters
      const signupUrl = new URL('/auth/signin', window.location.origin)
      signupUrl.searchParams.set('email', email)
      if (utmSource) signupUrl.searchParams.set('utm_source', utmSource)
      if (utmMedium) signupUrl.searchParams.set('utm_medium', utmMedium)
      if (utmCampaign) signupUrl.searchParams.set('utm_campaign', utmCampaign)

      window.location.href = signupUrl.toString()
    } catch (error) {
      console.error('Signup error:', error)
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-bg-primary via-bg-primary to-bg-secondary">
      {/* Minimal Header */}
      <header className="py-4 px-6">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="text-2xl font-bold text-gradient">
            Parlay Guarantee
          </div>
          <div className="text-sm text-accent-green">
            Money-Back Guarantee
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="max-w-4xl mx-auto px-6 py-12">
        <div className="text-center mb-12">
          <h1 className="text-5xl md:text-6xl font-bold mb-6">
            <span className="text-gradient">AI Sports Picks</span>
            <br />
            <span className="text-text-primary">That Actually Win</span>
          </h1>
          
          <p className="text-xl text-text-muted mb-8 max-w-2xl mx-auto">
            Our advanced AI model analyzes 38+ factors including real-time injury data, 
            team dynamics, and historical performance to deliver profitable picks.
          </p>

          {/* Social Proof Badge */}
          <div className="inline-flex items-center bg-accent-gold/10 border border-accent-gold/30 rounded-full px-6 py-3 mb-8">
            <span className="text-accent-gold font-bold text-lg">
              🔥 Our AI hit 7/10 spread covers on its first live night!
            </span>
          </div>

          {/* Key Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
            <div className="bg-bg-secondary/50 rounded-xl p-6 border border-accent-green/20">
              <div className="text-3xl font-bold text-accent-green mb-2">70%</div>
              <div className="text-text-muted text-sm">Spread Accuracy</div>
            </div>
            <div className="bg-bg-secondary/50 rounded-xl p-6 border border-accent-green/20">
              <div className="text-3xl font-bold text-accent-gold mb-2">74%</div>
              <div className="text-text-muted text-sm">Straight-Up Accuracy</div>
            </div>
            <div className="bg-bg-secondary/50 rounded-xl p-6 border border-accent-green/20">
              <div className="text-3xl font-bold text-accent-green mb-2">38+</div>
              <div className="text-text-muted text-sm">AI Factors</div>
            </div>
            <div className="bg-bg-secondary/50 rounded-xl p-6 border border-accent-green/20">
              <div className="text-3xl font-bold text-accent-gold mb-2">100%</div>
              <div className="text-text-muted text-sm">Money Back</div>
            </div>
          </div>
        </div>

        {/* Benefits Section */}
        <div className="grid md:grid-cols-2 gap-8 mb-12">
          <div>
            <h2 className="text-3xl font-bold text-accent-green mb-6">Why Our AI Wins</h2>
            <div className="space-y-4">
              <div className="flex items-start space-x-3">
                <div className="w-6 h-6 bg-accent-green rounded-full flex items-center justify-center flex-shrink-0 mt-1">
                  <span className="text-black text-sm font-bold">✓</span>
                </div>
                <div>
                  <h3 className="font-bold text-text-primary mb-1">Real-Time Injury Data</h3>
                  <p className="text-text-muted">Instant updates on player injuries and their impact on game outcomes</p>
                </div>
              </div>
              
              <div className="flex items-start space-x-3">
                <div className="w-6 h-6 bg-accent-green rounded-full flex items-center justify-center flex-shrink-0 mt-1">
                  <span className="text-black text-sm font-bold">✓</span>
                </div>
                <div>
                  <h3 className="font-bold text-text-primary mb-1">38-Factor AI Model</h3>
                  <p className="text-text-muted">Advanced algorithm analyzes team stats, weather, rest days, and more</p>
                </div>
              </div>
              
              <div className="flex items-start space-x-3">
                <div className="w-6 h-6 bg-accent-green rounded-full flex items-center justify-center flex-shrink-0 mt-1">
                  <span className="text-black text-sm font-bold">✓</span>
                </div>
                <div>
                  <h3 className="font-bold text-text-primary mb-1">Money-Back Guarantee</h3>
                  <p className="text-text-muted">If your picks don't profit, get a full refund. No questions asked.</p>
                </div>
              </div>
              
              <div className="flex items-start space-x-3">
                <div className="w-6 h-6 bg-accent-green rounded-full flex items-center justify-center flex-shrink-0 mt-1">
                  <span className="text-black text-sm font-bold">✓</span>
                </div>
                <div>
                  <h3 className="font-bold text-text-primary mb-1">Multiple Sports</h3>
                  <p className="text-text-muted">NBA, NFL, MLB, NHL, UFC, Soccer, College Basketball & Football</p>
                </div>
              </div>
            </div>
          </div>

          <div>
            <h2 className="text-3xl font-bold text-accent-gold mb-6">Get Started Today</h2>
            <div className="bg-bg-secondary border-2 border-accent-green/30 rounded-xl p-8">
              <div className="text-center mb-6">
                <div className="text-4xl font-bold text-accent-green mb-2">FREE</div>
                <div className="text-text-muted">First Pick Pack</div>
                <div className="text-sm text-accent-gold mt-2">No credit card required</div>
              </div>
              
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <input
                    type="email"
                    placeholder="Enter your email address"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="w-full bg-bg-primary border border-accent-green/20 rounded-lg px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-green text-lg"
                  />
                </div>
                
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className={`w-full font-bold py-4 px-6 rounded-lg text-lg transition-all duration-200 ${
                    isSubmitting 
                      ? 'bg-gray-600 cursor-not-allowed' 
                      : 'bg-accent-green hover:bg-accent-green/90 text-black hover:scale-105 hover:shadow-lg hover:shadow-accent-green/25'
                  }`}
                >
                  {isSubmitting ? 'Processing...' : 'Get My Free Picks Now'}
                </button>
              </form>
              
              <div className="text-center mt-4">
                <p className="text-xs text-text-muted">
                  Join 1,000+ winning bettors. Unsubscribe anytime.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Trust Signals */}
        <div className="text-center mb-8">
          <div className="flex flex-wrap justify-center items-center gap-8 text-text-muted text-sm">
            <div className="flex items-center space-x-2">
              <span className="text-accent-green">🔒</span>
              <span>Secure & Private</span>
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-accent-gold">⚡</span>
              <span>Instant Access</span>
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-accent-green">💯</span>
              <span>Money-Back Guarantee</span>
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-accent-gold">🏆</span>
              <span>Proven Results</span>
            </div>
          </div>
        </div>

        {/* Final CTA Section */}
        <div className="bg-gradient-to-r from-accent-green/10 to-accent-gold/10 border border-accent-green/30 rounded-2xl p-8 text-center">
          <h2 className="text-3xl font-bold text-text-primary mb-4">
            Don't Miss Tonight's Games
          </h2>
          <p className="text-xl text-text-muted mb-6">
            Our AI is generating picks for today's slate. Get your free pack now before tipoff.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <button 
              onClick={() => document.querySelector('input[type="email"]')?.scrollIntoView()}
              className="bg-accent-gold hover:bg-accent-gold/90 text-black font-bold py-4 px-8 rounded-lg text-lg transition-all duration-200 hover:scale-105"
            >
              Claim Your Free Picks
            </button>
            <p className="text-sm text-text-muted">
              ⏰ Limited time offer
            </p>
          </div>
        </div>
      </main>

      {/* Minimal Footer */}
      <footer className="py-8 px-6 border-t border-accent-green/10">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-xs text-text-muted mb-2">
            21+ | Gamble Responsibly | 
            <Link href="/terms" className="underline hover:text-accent-green ml-1 mr-1">Terms</Link> | 
            <Link href="/privacy" className="underline hover:text-accent-green ml-1">Privacy</Link>
          </p>
          <p className="text-xs text-text-muted opacity-70">
            Entertainment purposes only. Not a sportsbook.
          </p>
        </div>
      </footer>
    </div>
  )
}

export default function GoogleAdsLandingPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gradient-to-br from-bg-primary via-bg-primary to-bg-secondary flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-accent-green mx-auto"></div>
          <p className="text-text-muted mt-4">Loading...</p>
        </div>
      </div>
    }>
      <LandingPageContent />
    </Suspense>
  )
}