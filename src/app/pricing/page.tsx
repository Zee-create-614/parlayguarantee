'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { CheckCircle, Shield, Zap, Target, Crown, Trophy, ArrowRight, AlertTriangle } from 'lucide-react'
import Header from '../components/Header'
import { TIER_CONFIGS, TIER_ORDER, ML_TIER_CONFIGS, ML_TIER_ORDER } from '../../lib/tier-config'

const faqs = [
  {
    q: 'How does pricing work?',
    a: 'Each tier is a one-time charge. You pick the parlay size you want (single pick up to 7 legs), select your sport, pay, and get your AI-curated picks instantly. If any leg of your parlay loses, you get a full refund — no questions asked.',
  },
  {
    q: 'How are picks assigned?',
    a: 'All picks are auto-assigned by our AI engine. You select your sport, pay for a tier, and our model curates the best picks for you. No browsing games or choosing matchups — the AI does all the work.',
  },
  {
    q: 'What are the daily limits?',
    a: 'You can buy up to 3 two-leg parlays per day, and 1 each of all other tiers per day. This ensures every customer gets unique, high-quality picks.',
  },
  {
    q: 'Will I get duplicate picks if I buy multiple parlays?',
    a: 'Never. Every parlay you purchase on a given day contains unique picks. No duplicate legs across your purchases for the same day.',
  },
  {
    q: 'Do I get a free pick when I sign up?',
    a: 'Yes! Every new account gets a FREE 3-leg parlay — no purchase required. Just sign up, select your sport, and your free pick is assigned instantly.',
  },
  {
    q: 'How do referrals work?',
    a: 'Share your referral link. When a friend signs up, you BOTH get a free 3-leg parlay pick. No purchase required from either side.',
  },
  {
    q: 'How do refunds work?',
    a: 'Simple: if ANY leg of your parlay loses (or your single pick loses), you get a full refund processed within 24 hours. This applies to every tier. No fine print.',
  },
  {
    q: 'What sports are available?',
    a: 'Currently NBA and NCAAB (college basketball). You can also choose Mixed to get picks from both. More sports coming soon.',
  },
  {
    q: 'Is this gambling advice?',
    a: 'No. This is an AI-powered sports analysis service for entertainment and informational purposes. We provide predictions based on statistical modeling. Please gamble responsibly and only bet what you can afford to lose. 21+ only where legal.',
  },
]

export default function PricingPage() {
  const [selectedSport, setSelectedSport] = useState('NBA')
  const [pickType, setPickType] = useState<'spread' | 'moneyline'>('spread')

  const tiers = TIER_ORDER.map(id => TIER_CONFIGS[id])
  const mlTiers = ML_TIER_ORDER.map(id => ML_TIER_CONFIGS[id])

  const buildCheckoutUrl = (tierId: string) => {
    return `/checkout?tier=${tierId}&sports=${encodeURIComponent(selectedSport)}`
  }

  // Grid highlight configs
  const highlightTiers: Record<string, { glowColor: string; borderColor: string }> = {
    '2leg': { glowColor: 'rgba(0,255,136,0.15)', borderColor: 'border-accent-green' },
    '3leg': { glowColor: 'rgba(255,215,0,0.15)', borderColor: 'border-accent-gold' },
    '7leg': { glowColor: 'rgba(168,85,247,0.15)', borderColor: 'border-purple-400' },
  }

  return (
    <div className="min-h-screen bg-bg-primary">
      <Header />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 pb-12">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-4xl md:text-6xl font-bold mb-6">
            AI-Powered Picks. <span className="text-gradient">Guaranteed Refund.</span>
          </h1>
          <p className="text-xl text-text-muted mb-8 max-w-3xl mx-auto">
            Choose your tier. Every pick is AI-curated and auto-assigned.
            If any leg loses — full refund, every time.
          </p>

          <div className="flex flex-wrap gap-4 justify-center mb-8">
            <div className="guarantee-badge">
              <Shield className="w-4 h-4 mr-2" />
              FULL REFUND IF ANY LEG LOSES
            </div>
            <div className="guarantee-badge !border-accent-gold !text-accent-gold">
              <Zap className="w-4 h-4 mr-2" />
              ALL PICKS AUTO-ASSIGNED BY AI
            </div>
          </div>

          {/* Pick Type Toggle */}
          <div className="flex justify-center gap-2 mb-6">
            <button
              onClick={() => setPickType('spread')}
              className={`px-6 py-3 rounded-lg text-sm font-bold transition-all ${
                pickType === 'spread'
                  ? 'bg-accent-green text-black shadow-lg shadow-accent-green/20'
                  : 'bg-bg-secondary text-text-muted hover:bg-bg-secondary/80'
              }`}
            >
              🎯 Spread Picks
            </button>
            <button
              onClick={() => setPickType('moneyline')}
              className={`px-6 py-3 rounded-lg text-sm font-bold transition-all ${
                pickType === 'moneyline'
                  ? 'bg-accent-gold text-black shadow-lg shadow-accent-gold/20'
                  : 'bg-bg-secondary text-text-muted hover:bg-bg-secondary/80'
              }`}
            >
              💰 Moneyline Picks
            </button>
          </div>

          {/* Sport Selector */}
          <div className="flex justify-center gap-3 mb-4">
            {['NBA', 'NCAAB', 'Mixed (NBA + NCAAB)'].map((sport) => (
              <button
                key={sport}
                onClick={() => setSelectedSport(sport)}
                className={`px-5 py-2.5 rounded-full text-sm font-bold transition-all ${
                  selectedSport === sport
                    ? 'bg-accent-green text-black'
                    : 'bg-bg-secondary text-text-muted hover:bg-bg-secondary/80'
                }`}
              >
                {sport}
              </button>
            ))}
          </div>
        </div>

        {/* Free Signup Banner */}
        <div className="mb-12 relative overflow-hidden rounded-2xl border-2 border-accent-green/40 bg-gradient-to-r from-accent-green/10 via-accent-gold/5 to-accent-green/10">
          <div className="relative p-8 text-center">
            <div className="text-4xl mb-3">🎁</div>
            <h3 className="text-2xl font-extrabold text-accent-green mb-2">FREE 3-Leg Parlay on Signup</h3>
            <p className="text-lg text-text-muted max-w-xl mx-auto mb-4">
              Every new account gets a free 3-leg parlay — no purchase required. Sign up, pick your sport, and your free pick is assigned instantly.
            </p>
            <Link href="/auth/signin" className="btn-primary px-8 py-3 inline-block">
              Sign Up & Get Your Free Pick →
            </Link>
          </div>
        </div>

        {/* Pricing Cards */}
        <div className="grid lg:grid-cols-4 md:grid-cols-3 sm:grid-cols-2 gap-5 mb-20">
          {(pickType === 'spread' ? tiers : mlTiers).map((tier) => {
            const hl = highlightTiers[tier.id]
            const isHighlighted = !!hl

            return (
              <div
                key={tier.id}
                className={`card border-2 ${hl?.borderColor || 'border-white/10'} ${
                  hl?.glowColor ? `shadow-[0_0_40px_${hl.glowColor}]` : ''
                } bg-gradient-to-b from-bg-secondary/80 to-bg-primary p-5 relative flex flex-col`}
              >
                {tier.badge && (
                  <div className="absolute -top-3 left-1/2 transform -translate-x-1/2">
                    <span className={`bg-${tier.badgeColor} text-black px-4 py-1 rounded-full text-xs font-bold whitespace-nowrap`}>
                      {tier.badge}
                    </span>
                  </div>
                )}

                <div className="text-center flex-1 flex flex-col">
                  <div className="text-3xl mb-2">{tier.icon}</div>
                  <h3 className="text-lg font-bold mb-0.5">{tier.name}</h3>
                  <p className="text-xs text-text-muted mb-3">
                    {tier.dailyLimit === 1 ? '1x per day' : `${tier.dailyLimit}x per day`}
                  </p>

                  <div className="mb-3">
                    <div className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-accent-green to-accent-gold mb-1">
                      ${tier.price}
                    </div>
                    <div className="text-xs text-text-muted">one-time charge</div>
                  </div>

                  <p className="text-sm text-text-muted mb-3">{tier.description}</p>

                  {/* Guarantee */}
                  <div className="bg-accent-green/10 border border-accent-green/30 rounded-lg p-2.5 mb-3">
                    <div className="flex items-center justify-center gap-2 text-accent-green text-xs font-semibold">
                      <Shield className="w-3.5 h-3.5" />
                      {tier.guarantee}
                    </div>
                  </div>

                  {/* Features */}
                  <ul className="space-y-1.5 mb-4 text-left text-xs flex-1">
                    {[
                      `${tier.legs === 1 ? '1 AI-curated moneyline pick' : `${tier.legs} AI-curated parlay legs`}`,
                      'Picks auto-assigned instantly',
                      'No duplicate legs across purchases',
                      `Full refund if ${tier.legs === 1 ? 'it loses' : 'any leg loses'}`,
                      'Sport selection at checkout',
                    ].map((feature, i) => (
                      <li key={i} className="flex items-start">
                        <CheckCircle className="w-3.5 h-3.5 text-accent-green mr-1.5 flex-shrink-0 mt-0.5" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>

                  {/* CTA */}
                  <Link
                    href={buildCheckoutUrl(tier.id)}
                    className={`w-full py-2.5 px-4 rounded-lg font-bold text-sm text-center transition-all inline-block ${
                      isHighlighted
                        ? 'bg-gradient-to-r from-accent-green to-emerald-400 text-black hover:opacity-90'
                        : 'btn-primary'
                    }`}
                  >
                    Get {tier.name} <ArrowRight className="w-3.5 h-3.5 inline ml-1" />
                  </Link>
                  <p className="text-[10px] text-text-muted mt-2">
                    Charged ${tier.price}. Full refund within 24h if {tier.legs === 1 ? 'it loses' : 'any leg loses'}.
                  </p>
                </div>
              </div>
            )
          })}
        </div>

        {/* Referral Bonus */}
        <div className="mb-20 relative overflow-hidden rounded-2xl border-2 border-purple-500/40 bg-gradient-to-r from-purple-500/10 via-accent-gold/5 to-purple-500/10">
          <div className="relative p-8 md:p-10 text-center">
            <div className="text-5xl mb-4">🤝</div>
            <h3 className="text-3xl font-extrabold text-purple-400 mb-3">Refer a Friend — Both Get a Free 3-Leg Pick</h3>
            <p className="text-lg text-text-muted max-w-2xl mx-auto mb-6">
              Share your referral link. When a friend signs up, you <span className="text-accent-green font-bold">BOTH</span> get a <span className="text-accent-gold font-bold">FREE 3-Leg Parlay Pick</span> — no purchase required.
            </p>
            <Link href="/auth/signin" className="bg-purple-500 hover:bg-purple-600 text-white font-bold px-8 py-3 rounded-lg transition-all inline-block">
              Sign Up & Get Your Referral Link
            </Link>
          </div>
        </div>

        {/* How It Works */}
        <div className="grid md:grid-cols-4 gap-6 mb-20">
          {[
            { icon: <Target className="w-7 h-7 text-black" />, bg: 'bg-accent-green', title: '1. Pick Your Tier', desc: 'Choose from single pick to 7-leg parlay. Select your sport.' },
            { icon: <Crown className="w-7 h-7 text-black" />, bg: 'bg-accent-gold', title: '2. AI Assigns Picks', desc: 'Our 37-factor model curates your picks instantly. No choosing games.' },
            { icon: <Shield className="w-7 h-7 text-black" />, bg: 'bg-accent-green', title: '3. You\'re Protected', desc: 'If ANY leg loses, full refund. Every tier, every time.' },
            { icon: <Trophy className="w-7 h-7 text-black" />, bg: 'bg-accent-gold', title: '4. Check Dashboard', desc: 'See your picks, results, and refund status in your account.' },
          ].map((step, i) => (
            <div key={i} className="text-center">
              <div className={`w-14 h-14 ${step.bg} rounded-full flex items-center justify-center mx-auto mb-4`}>
                {step.icon}
              </div>
              <h3 className="text-lg font-bold mb-2">{step.title}</h3>
              <p className="text-sm text-text-muted">{step.desc}</p>
            </div>
          ))}
        </div>

        {/* FAQ */}
        <div className="mb-20">
          <h2 className="text-3xl font-bold text-center mb-12">Frequently Asked Questions</h2>
          <div className="max-w-4xl mx-auto space-y-4">
            {faqs.map((faq, index) => (
              <div key={index} className="card p-5">
                <h3 className="text-base font-bold mb-2 text-accent-green">{faq.q}</h3>
                <p className="text-sm text-text-muted leading-relaxed">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Refund Policy */}
        <div className="card mb-20 p-8 border-accent-green/30">
          <h3 className="text-2xl font-bold text-center mb-6">📋 Refund Policy</h3>
          <div className="max-w-3xl mx-auto space-y-4 text-sm text-text-muted">
            <div className="flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-accent-green flex-shrink-0 mt-0.5" />
              <p><strong className="text-text-primary">All tiers (Single through 7-leg):</strong> If your pick loses (or ANY leg of your parlay loses), we process a full refund within 24 hours. No action required on your end.</p>
            </div>
            <div className="flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-accent-green flex-shrink-0 mt-0.5" />
              <p><strong className="text-text-primary">Simple charge model:</strong> Your card is charged at purchase. If it loses, you get a full refund — simple as that.</p>
            </div>
            <div className="flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-accent-green flex-shrink-0 mt-0.5" />
              <p><strong className="text-text-primary">Processing time:</strong> Refunds typically appear within 1-3 business days depending on your bank.</p>
            </div>
          </div>
        </div>

        {/* Final CTA */}
        <div className="text-center bg-gradient-to-r from-accent-green/10 to-accent-gold/10 rounded-2xl p-12">
          <h2 className="text-3xl font-bold mb-4">Start With a Single Pick for $5</h2>
          <p className="text-xl text-text-muted mb-8">
            No subscription. No commitment. AI-curated picks with a full refund guarantee.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/checkout?tier=single&sports=NBA" className="btn-primary text-lg py-4 px-8">
              Get Today&apos;s Pick — $5
            </Link>
            <Link href="/auth/signin" className="btn-secondary text-lg py-4 px-8">
              Sign Up for Free Pick
            </Link>
          </div>
        </div>

        {/* Legal */}
        <div className="mt-12 p-6 bg-bg-secondary/30 rounded-lg border border-accent-green/20">
          <p className="text-sm text-text-muted text-center">
            <strong>Important:</strong> This service is for entertainment and educational purposes only.
            We do not provide gambling advice. Please gamble responsibly and only bet what you can afford to lose.
            21+ only where legal. Past performance does not guarantee future results.
          </p>
        </div>
      </div>
    </div>
  )
}
