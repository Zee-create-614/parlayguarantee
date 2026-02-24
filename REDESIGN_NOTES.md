# ParlayGuarantee.com — Redesign Notes

**Date:** 2026-02-23
**Scope:** Frontend-only redesign. No backend/API/engine changes.

## Design Direction

Premium dark luxury aesthetic inspired by DraftKings, PrizePicks, and Underdog Fantasy — but more sophisticated. Black/gold/white color palette with glass-morphism, subtle gradients, and smooth CSS animations.

**Positioning:** "The Parlay Marketplace" — bold hero tagline.

## Files Changed

### 1. `tailwind.config.ts`
- New color palette: deeper blacks (`#050507`, `#0f0f17`), refined gold (`#D4AF37`, `#F5D77A`), glass colors
- Added `bg-tertiary`, `glass`, `glass-border` colors
- 10+ new animations: `float`, `gradient-x`, `gradient-slow`, `shine`, `fade-up` (with staggered delays), `slide-in-right`, `scale-in`
- Custom keyframes for all animations
- `bg-300%` utility for animated gradient backgrounds

### 2. `src/app/globals.css`
- Complete overhaul of component classes
- New `.card-premium` with top-line gold gradient and glassmorphism
- New `.glass-panel` for frosted glass sections
- New `.section-label` for consistent section headers
- `.btn-primary` now gold gradient with hover glow
- `.btn-secondary` now transparent with gold border
- `.text-gradient-hero` with animated shimmer
- `.hero-gradient` with multi-layered radial gradients
- `.grid-bg` subtle grid line pattern
- `.noise` SVG noise texture overlay
- Refined scrollbar (thinner, gold-tinted)
- Selection color matches gold theme

### 3. `src/app/page.tsx`
- **Hero:** Full-viewport, "The Parlay Marketplace" as main H1, animated gradient text, decorative blur orbs, staggered fade-up animations, trust bar below CTAs
- **Stats Bar:** Floating glass panel with animated counters (IntersectionObserver-triggered)
- **Tier Overview:** Premium cards with gold top-line, hover effects, free signup card with gold gradient
- **How It Works:** 4-step flow with gradient icon tiles, step numbers, hover rotate effect
- **Why ParlayGuarantee:** 3 feature cards with gradient icons
- **Social Proof:** 3 testimonial cards with star ratings and verified badges
- **Referral Section:** Gold gradient card with blur orb decoration
- **Final CTA:** Large centered section with gradient text
- **FAQ:** Premium cards with gold-tinted question text
- **AnimatedNumber component:** Scroll-triggered counter with easing

### 4. `src/app/components/Header.tsx`
- Fixed header with scroll-aware background (transparent → frosted glass on scroll)
- Stacked logo text (PARLAY / GUARANTEE) with tracking
- Refined nav with hover states, separator line
- Mobile menu with gold accent theme
- Smaller, more premium proportions

### 5. `src/app/layout.tsx`
- Removed old gradient wrapper (`bg-gradient-to-br`) for cleaner bg

## What Was NOT Changed
- No API routes, backend logic, or engine code
- No other page files (pricing, dashboard, blog, etc.)
- No package.json dependencies added (all CSS animations, no framer-motion needed)
- No deployment config

## Running Locally
```bash
cd parlayguarantee
npm run dev
# → http://localhost:3000
```

Confirmed: `npm run dev` returns HTTP 200 on localhost:3000.
