'use client'

import { useEffect, useState, useRef } from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { Shield, ArrowRight, Brain, Target, Zap, Trophy, Star, TrendingUp, Users, ChevronRight, Gift, Clock, DollarSign, BarChart3 } from 'lucide-react'
import Header from './components/Header'

/* ─── Animated Counter ─── */
function AnimatedNumber({ value, suffix = '', prefix = '' }: { value: number; suffix?: string; prefix?: string }) {
  const [display, setDisplay] = useState(0)
  const ref = useRef<HTMLDivElement>(null)
  const started = useRef(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !started.current) {
        started.current = true
        const duration = 1800
        const start = performance.now()
        const step = (now: number) => {
          const t = Math.min((now - start) / duration, 1)
          const ease = 1 - Math.pow(1 - t, 3)
          setDisplay(Math.round(value * ease))
          if (t < 1) requestAnimationFrame(step)
        }
        requestAnimationFrame(step)
      }
    }, { threshold: 0.3 })
    obs.observe(el)
    return () => obs.disconnect()
  }, [value])

  return <div ref={ref}>{prefix}{display.toLocaleString()}{suffix}</div>
}

/* ─── Sportsbook Track Record ─── */
function SportsbookTrackRecord() {
  const [data, setData] = useState<{ books: Array<{ name: string; logo?: string; winRate: number; totalPicks: number; correct: number }>; message?: string } | null>(null)

  useEffect(() => {
    fetch('/api/results/by-book').then(r => r.json()).then(d => setData(d)).catch(() => {})
  }, [])

  if (!data || !data.books || data.books.length === 0) return null

  return (
    <section className="py-24 px-4 relative">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-12">
          <div className="section-label"><TrendingUp className="w-3.5 h-3.5 mr-2" />VERIFIED RESULTS</div>
          <h2 className="font-display text-3xl md:text-5xl font-bold mb-4">Track Record by Sportsbook</h2>
          <p className="text-text-muted max-w-xl mx-auto">Live win rates across every platform our users bet on.</p>
        </div>
        <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-hide">
          {data.books.map((book, i) => (
            <div key={i} className="card-premium min-w-[180px] text-center flex-shrink-0 p-5">
              <div className="text-3xl mb-3">{book.logo || '📱'}</div>
              <h3 className="font-bold text-sm mb-2 text-text-muted">{book.name}</h3>
              <div className="text-3xl font-display font-bold text-gradient-green">{(book.winRate * 100).toFixed(1)}%</div>
              <p className="text-xs text-text-muted mt-1">{book.correct}/{book.totalPicks} picks</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Main Page ─── */
export default function HomePage() {
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search)
      const ref = params.get('ref')
      if (ref) sessionStorage.setItem('parlayguarantee_ref', ref)
    }
  }, [])

  const tiers = [
    { name: 'Single Pick', price: '$5', icon: '🎯', legs: '1 pick', popular: false },
    { name: '2-Leg Parlay', price: '$10', icon: '🔥', legs: '2 legs', popular: false },
    { name: '3-Leg Parlay', price: '$20', icon: '⚡', legs: '3 legs', popular: true },
    { name: '4-Leg Parlay', price: '$35', icon: '💎', legs: '4 legs', popular: false },
    { name: '5-Leg Parlay', price: '$50', icon: '👑', legs: '5 legs', popular: false },
    { name: '6-Leg Parlay', price: '$75', icon: '🏆', legs: '6 legs', popular: false },
    { name: '7-Leg Parlay', price: '$100', icon: '🚀', legs: '7 legs', popular: false },
  ]

  return (
    <div className="min-h-screen bg-bg-primary overflow-hidden">
      <Header />

      {/* ═══════════════ HERO ═══════════════ */}
      <section className="relative min-h-[100vh] flex items-center justify-center hero-gradient noise grid-bg">
        {/* Neon orbs */}
        <div className="absolute top-1/4 left-1/4 w-[600px] h-[600px] bg-neon/[0.06] rounded-full blur-[150px] animate-float" />
        <div className="absolute bottom-1/3 right-1/4 w-[400px] h-[400px] bg-neon/[0.04] rounded-full blur-[120px] animate-float" style={{ animationDelay: '3s' }} />

        <div className="relative z-10 max-w-6xl mx-auto px-4 text-center pt-24 pb-20">
          {/* Marketplace Title */}
          <div className="opacity-0-init animate-fade-up mb-4">
            <h1 className="font-display text-5xl sm:text-7xl md:text-[5.5rem] font-bold tracking-tight leading-[0.95]">
              <span className="bg-gradient-to-r from-neon to-orange-500 bg-clip-text text-transparent">The Parlay Marketplace</span>
            </h1>
          </div>

          {/* Badge */}
          <div className="opacity-0-init animate-fade-up mb-8">
            <span className="guarantee-badge">
              <Shield className="w-3.5 h-3.5 mr-2" />
              MONEY-BACK GUARANTEE ON EVERY PICK
            </span>
          </div>

          {/* Main headline */}
          <h2 className="opacity-0-init animate-fade-up-delay-1 font-display text-2xl md:text-3xl font-bold tracking-wide mb-6">
            <span className="text-white">AI-Powered</span>
            {' '}
            <span className="text-neon glow-neon">Sports Picks</span>
          </h2>

          {/* Sub */}
          <p className="opacity-0-init animate-fade-up-delay-2 text-lg md:text-xl text-text-muted max-w-2xl mx-auto mb-10 leading-relaxed">
            <span className="text-orange-500 font-semibold">37-factor adaptive engine that learns from every game — getting sharper, smarter, and more accurate daily.</span>
            {' '}7 tiers. Every pick auto-assigned for maximum edge.
            <span className="text-neon font-semibold"> If any leg loses, full refund. Period.</span>
          </p>

          {/* CTAs */}
          <div className="opacity-0-init animate-fade-up-delay-3 flex flex-col sm:flex-row gap-4 justify-center items-center mb-14">
            <Link href="/pricing" className="btn-primary text-base md:text-lg py-4 px-10 flex items-center group font-display">
              Browse Picks
              <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link href="/auth/signin" className="btn-secondary text-base md:text-lg py-4 px-10 flex items-center font-display">
              <Gift className="w-5 h-5 mr-2" /> Free 3-Leg Pick
            </Link>
          </div>

          {/* Trust bar */}
          <div className="opacity-0-init animate-fade-up-delay-4 flex flex-wrap justify-center gap-8 md:gap-12 text-sm text-text-muted">
            <span className="flex items-center gap-2"><Shield className="w-4 h-4 text-neon" /> Full Refund</span>
            <span className="flex items-center gap-2"><Zap className="w-4 h-4 text-neon" /> Instant Delivery</span>
            <span className="flex items-center gap-2"><Brain className="w-4 h-4 text-neon" /> 37-Factor AI</span>
            <span className="flex items-center gap-2"><Clock className="w-4 h-4 text-neon" /> Daily Picks</span>
          </div>
        </div>

        {/* Bottom fade */}
        <div className="absolute bottom-0 left-0 right-0 h-40 bg-gradient-to-t from-bg-primary to-transparent" />
      </section>

      {/* ═══════════════ LIVE STATS BAR ═══════════════ */}
      <section className="relative -mt-20 z-20 px-4 mb-24">
        <div className="max-w-5xl mx-auto">
          <div className="glass-panel border-orange-500/40 p-1">
            <div className="grid grid-cols-2 md:grid-cols-4">
              {[
                { value: 37, suffix: '', label: 'AI Factors', prefix: '', icon: Brain },
                { value: 7, suffix: '', label: 'Pick Tiers', prefix: '', icon: BarChart3 },
                { value: 100, suffix: '%', label: 'Loss Refund', prefix: '', icon: Shield },
                { value: 24, suffix: 'h', label: 'Refund Time', prefix: '<', icon: Clock },
              ].map((s, i) => (
                <div key={i} className={`text-center py-7 px-4 ${i < 3 ? 'border-r border-orange-500/30' : ''}`}>
                  <s.icon className="w-5 h-5 text-neon/60 mx-auto mb-2" />
                  <div className="text-2xl md:text-3xl font-display font-bold text-neon">
                    <AnimatedNumber value={s.value} suffix={s.suffix} prefix={s.prefix} />
                  </div>
                  <div className="text-[11px] text-text-muted mt-1 tracking-wider uppercase">{s.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════ HOW IT WORKS ═══════════════ */}
      <section className="py-24 px-4 relative">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-neon/[0.01] to-transparent" />
        <div className="max-w-5xl mx-auto relative z-10">
          <div className="text-center mb-16">
            <div className="section-label"><Zap className="w-3.5 h-3.5 mr-2" />HOW IT WORKS</div>
            <h2 className="font-display text-3xl md:text-5xl font-bold mb-4">Pick. Pay. <span className="text-neon">Profit.</span></h2>
            <p className="text-text-muted max-w-lg mx-auto">Four steps between you and AI-backed picks with zero risk.</p>
          </div>

          <div className="grid md:grid-cols-4 gap-6">
            {[
              { step: '01', title: 'Sign Up Free', desc: 'Create an account. Get a free 3-leg parlay instantly.', icon: Users },
              { step: '02', title: 'Choose a Tier', desc: 'Single picks ($5) to 7-leg parlays ($100). You pick the tier.', icon: Target },
              { step: '03', title: 'AI Assigns Picks', desc: '37 factors analyzed per game. No duplicates. Maximum edge.', icon: Brain },
              { step: '04', title: 'Win or Refund', desc: 'Any leg loses? Full refund. No questions. Under 24 hours.', icon: Shield },
            ].map((s, i) => (
              <div key={i} className="relative group">
                {/* Connector line */}
                {i < 3 && <div className="hidden md:block absolute top-8 left-[60%] w-[80%] h-px bg-gradient-to-r from-neon/20 to-transparent" />}
                <div className="relative bg-bg-card border border-white/[0.06] rounded-2xl p-6 hover:border-neon/30 transition-all duration-500 hover:shadow-[0_0_30px_rgba(0,255,135,0.06)]">
                  <div className="w-14 h-14 bg-neon/10 border border-neon/20 rounded-xl flex items-center justify-center mb-5 group-hover:bg-neon/20 transition-colors">
                    <s.icon className="w-6 h-6 text-neon" />
                  </div>
                  <div className="font-display text-[11px] font-bold tracking-[0.3em] text-neon/40 mb-2">STEP {s.step}</div>
                  <h3 className="font-display text-lg font-bold mb-2">{s.title}</h3>
                  <p className="text-sm text-text-muted leading-relaxed">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════ TIER GRID ═══════════════ */}
      <section className="py-24 px-4 relative">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <div className="section-label"><Trophy className="w-3.5 h-3.5 mr-2" />PICK YOUR TIER</div>
            <h2 className="font-display text-3xl md:text-5xl font-bold mb-4">7 Tiers. <span className="text-neon">One Guarantee.</span></h2>
            <p className="text-text-muted max-w-xl mx-auto">Every tier includes a full refund if any leg loses. Scale your risk, keep your edge.</p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 mb-6">
            {tiers.map((t, i) => (
              <Link href="/pricing" key={i} className={`relative group cursor-pointer rounded-2xl p-5 text-center transition-all duration-500 border ${
                t.popular 
                  ? 'bg-neon/[0.08] border-neon/40 hover:border-neon/70 hover:shadow-[0_0_40px_rgba(0,255,135,0.12)]' 
                  : 'bg-bg-card border-white/[0.06] hover:border-neon/30 hover:shadow-[0_0_30px_rgba(0,255,135,0.06)]'
              }`}>
                {t.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-neon text-black text-[10px] font-bold rounded-full tracking-wider">
                    POPULAR
                  </div>
                )}
                <div className="text-3xl mb-3 group-hover:scale-110 transition-transform duration-300">{t.icon}</div>
                <h3 className="font-display font-bold text-sm text-text-primary mb-1">{t.name}</h3>
                <div className="text-2xl font-display font-bold text-neon mb-1">{t.price}</div>
                <p className="text-xs text-text-muted">{t.legs}</p>
              </Link>
            ))}
            {/* Free card */}
            <Link href="/auth/signin" className="relative group cursor-pointer rounded-2xl p-5 text-center transition-all duration-500 border border-neon/30 bg-gradient-to-b from-neon/[0.06] to-transparent hover:border-neon/60 hover:shadow-[0_0_40px_rgba(0,255,135,0.1)]">
              <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-neon to-transparent" />
              <div className="text-3xl mb-3 group-hover:scale-110 transition-transform duration-300">🎁</div>
              <h3 className="font-display font-bold text-sm text-neon mb-1">Free on Signup</h3>
              <div className="text-2xl font-display font-bold text-white">FREE</div>
              <p className="text-xs text-text-muted">3-leg parlay</p>
            </Link>
          </div>

          <div className="text-center mt-10">
            <Link href="/pricing" className="btn-primary text-base py-4 px-10 inline-flex items-center group font-display">
              View Full Pricing <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </div>
      </section>

      {/* ═══════════════ SPORTSBOOK TRACK RECORD ═══════════════ */}
      <SportsbookTrackRecord />

      {/* ═══════════════ WHY US ═══════════════ */}
      <section className="py-24 px-4 relative">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <div className="section-label"><Star className="w-3.5 h-3.5 mr-2" />THE EDGE</div>
            <h2 className="font-display text-3xl md:text-5xl font-bold mb-4">Why <span className="text-neon">ParlayGuarantee</span>?</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                icon: Brain,
                title: '37-Factor AI Model',
                desc: 'Offensive/defensive ratings, injuries, rest days, line movement, and 30+ factors analyzed per game.',
              },
              {
                icon: Shield,
                title: 'Full Refund Guarantee',
                desc: 'Every tier, every purchase. If any leg loses, money back. Period. No fine print.',
              },
              {
                icon: Target,
                title: 'Auto-Assigned Picks',
                desc: 'No guessing. Our AI selects the highest-edge matchups for your sport and tier.',
              },
            ].map((f, i) => (
              <div key={i} className="group bg-bg-card border border-white/[0.06] rounded-2xl p-8 hover:border-neon/30 transition-all duration-500 hover:shadow-[0_0_30px_rgba(0,255,135,0.06)]">
                <div className="w-14 h-14 bg-neon/10 border border-neon/20 rounded-xl flex items-center justify-center mb-5 group-hover:bg-neon/20 group-hover:scale-110 transition-all duration-300">
                  <f.icon className="w-6 h-6 text-neon" />
                </div>
                <h3 className="font-display text-lg font-bold mb-3">{f.title}</h3>
                <p className="text-sm text-text-muted leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════ TESTIMONIALS ═══════════════ */}
      <section className="py-24 px-4 relative">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-neon/[0.01] to-transparent" />
        <div className="max-w-5xl mx-auto relative z-10">
          <div className="text-center mb-16">
            <div className="section-label"><Users className="w-3.5 h-3.5 mr-2" />SOCIAL PROOF</div>
            <h2 className="font-display text-3xl md:text-5xl font-bold mb-4">What Bettors Are Saying</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              { quote: "Got my refund in under 12 hours. These guys are legit. Already bought 3 more tiers.", author: "Marcus T.", tier: "5-Leg Parlay", stars: 5 },
              { quote: "The AI picks are actually insane. Hit a 4-legger on my first try. Withdrew $400 from DraftKings.", author: "Jake R.", tier: "4-Leg Parlay", stars: 5 },
              { quote: "Free 3-leg hit on my first day. I was skeptical but this is real. Refer your friends.", author: "Destiny W.", tier: "Free Pick", stars: 5 },
            ].map((t, i) => (
              <div key={i} className="bg-bg-card border border-white/[0.06] rounded-2xl p-6 hover:border-neon/20 transition-all duration-500">
                <div className="flex gap-0.5 mb-4">
                  {Array.from({ length: t.stars }).map((_, j) => (
                    <Star key={j} className="w-4 h-4 fill-neon text-neon" />
                  ))}
                </div>
                <p className="text-sm text-text-primary/80 mb-4 leading-relaxed italic">&ldquo;{t.quote}&rdquo;</p>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-bold">{t.author}</div>
                    <div className="text-xs text-text-muted">{t.tier}</div>
                  </div>
                  <div className="text-neon text-xs font-bold">✓ Verified</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════ REFERRAL ═══════════════ */}
      <section className="py-24 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="relative overflow-hidden rounded-3xl border border-neon/20 bg-gradient-to-br from-neon/[0.06] via-transparent to-neon/[0.02] p-10 md:p-14 text-center">
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-neon to-transparent" />
            <div className="absolute -top-20 -right-20 w-60 h-60 bg-neon/[0.06] rounded-full blur-[80px]" />
            <div className="relative z-10">
              <div className="text-5xl mb-5">🤝</div>
              <h2 className="font-display text-3xl md:text-4xl font-bold mb-4">Refer a Friend</h2>
              <p className="text-lg text-text-muted mb-8 max-w-xl mx-auto">
                Share your link. When a friend signs up, you <span className="text-neon font-bold">BOTH</span> get a <span className="text-neon font-bold">FREE 3-Leg Parlay</span>.
              </p>
              <Link href="/auth/signin" className="btn-primary text-base py-4 px-10 inline-flex items-center group font-display">
                Start Referring <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════ FINAL CTA ═══════════════ */}
      <section className="py-28 px-4 relative">
        <div className="absolute inset-0 hero-gradient opacity-50" />
        <div className="max-w-3xl mx-auto text-center relative z-10">
          <h2 className="font-display text-4xl md:text-6xl font-bold mb-6 leading-tight">
            Your Edge Starts<br /><span className="text-neon glow-neon">Today.</span>
          </h2>
          <p className="text-lg text-text-muted mb-10 max-w-xl mx-auto">
            Sign up free and claim your 3-leg parlay. Or jump straight to pricing.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Link href="/auth/signin" className="btn-primary text-lg py-5 px-10 flex items-center group font-display">
              🎁 Claim Free Pick
              <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link href="/pricing" className="btn-secondary text-lg py-5 px-10 font-display">
              View Pricing
            </Link>
          </div>
        </div>
      </section>

      {/* ═══════════════ FAQ ═══════════════ */}
      <section className="py-24 px-4">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="font-display text-3xl md:text-4xl font-bold">Frequently Asked Questions</h2>
          </div>
          <div className="space-y-4">
            {[
              { q: "How does the guarantee work?", a: "You pay for a tier, we auto-assign picks. If any leg loses, full refund within 24 hours. No questions asked." },
              { q: "Do I get to choose my picks?", a: "No — by design. Our AI selects the highest-edge picks for your tier and sport. You pick the sport, we handle the rest." },
              { q: "What do I get for free?", a: "Every new account gets a FREE 3-leg parlay pick. No credit card required. Just sign up and select your sport." },
              { q: "What sports do you cover?", a: "Currently NBA, NHL, and UFC/MMA. More sports coming soon." },
              { q: "Is this gambling advice?", a: "No. AI-generated sports analysis for entertainment purposes only. Please gamble responsibly. 21+ only where legal." },
            ].map((faq, i) => (
              <div key={i} className="bg-bg-card border border-white/[0.06] rounded-2xl p-6 hover:border-neon/20 transition-all duration-300">
                <h3 className="font-display text-base font-bold mb-2 text-neon">{faq.q}</h3>
                <p className="text-sm text-text-muted leading-relaxed">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
