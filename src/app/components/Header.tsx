'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { Menu, X, ChevronRight } from 'lucide-react'

const navLinks = [
  { name: 'Home', href: '/' },
  { name: 'Pricing', href: '/pricing' },
  { name: 'Results', href: '/results' },
  { name: 'Blog', href: '/blog' },
]

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [loggedIn, setLoggedIn] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    fetch('/api/auth/me').then(r => r.json()).then(d => setLoggedIn(!!d.authenticated)).catch(() => {})
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <>
      <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${
        scrolled
          ? 'bg-black backdrop-blur-xl border-b border-neon/10 shadow-[0_4px_30px_rgba(0,0,0,0.3)]'
          : 'bg-black/95 border-b border-white/[0.06]'
      }`}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <Link href="/" className="flex items-center gap-3 group">
              <Image src="/parlay-logo-new.png" alt="Parlay Guarantee" width={56} height={56} className="" />
              <div className="flex flex-col">
                <span className="text-2xl md:text-3xl font-display font-bold text-gradient tracking-tight leading-tight">PARLAY</span>
                <span className="text-[11px] md:text-xs font-bold tracking-[0.3em] text-orange-500 leading-tight">GUARANTEE</span>
              </div>
            </Link>

            {/* Desktop Nav */}
            <nav className="hidden md:flex items-center space-x-1">
              {navLinks.map(link => (
                <Link key={link.name} href={link.href} className="px-4 py-2 text-sm font-medium text-text-muted hover:text-neon transition-colors duration-300 rounded-lg hover:bg-white/[0.03]">
                  {link.name}
                </Link>
              ))}
              <div className="w-px h-6 bg-white/10 mx-2" />
              {loggedIn ? (
                <Link href="/dashboard" className="btn-primary text-sm py-2 px-5">Dashboard</Link>
              ) : (
                <>
                  <Link href="/auth/signin" className="px-4 py-2 text-sm font-medium text-text-muted hover:text-white transition-colors">Sign In</Link>
                  <Link href="/auth/signin" className="btn-primary text-sm py-2 px-5">Join Waitlist</Link>
                </>
              )}
            </nav>

            {/* Mobile hamburger */}
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="md:hidden p-2 rounded-lg hover:bg-white/[0.05] transition-colors"
              aria-label="Menu"
            >
              {menuOpen ? <X className="w-5 h-5 text-neon" /> : <Menu className="w-5 h-5 text-neon" />}
            </button>
          </div>
        </div>
      </header>

      {/* Mobile menu overlay */}
      {menuOpen && (
        <div className="fixed inset-0 z-[60]" onClick={() => setMenuOpen(false)}>
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
          <div
            className="absolute right-0 top-0 h-full w-80 max-w-[85vw] bg-bg-secondary/95 backdrop-blur-xl border-l border-neon/10 shadow-2xl overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <div className="flex justify-between items-center mb-10">
                <span className="text-sm font-bold tracking-[0.2em] text-neon uppercase">Menu</span>
                <button onClick={() => setMenuOpen(false)} className="p-2 hover:bg-white/[0.05] rounded-lg">
                  <X className="w-5 h-5 text-text-muted" />
                </button>
              </div>

              <div className="space-y-1 mb-10">
                {navLinks.map(link => (
                  <Link
                    key={link.name}
                    href={link.href}
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center justify-between p-3 rounded-xl hover:bg-white/[0.04] transition-all duration-300 group"
                  >
                    <span className="text-text-primary group-hover:text-neon transition-colors">{link.name}</span>
                    <ChevronRight className="w-4 h-4 text-text-muted group-hover:text-neon transition-colors" />
                  </Link>
                ))}
                <Link
                  href={loggedIn ? "/dashboard" : "/auth/signin"}
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center justify-between p-3 rounded-xl hover:bg-white/[0.04] transition-all duration-300"
                >
                  <span className="text-neon font-medium">{loggedIn ? "Dashboard" : "Sign In"}</span>
                  <ChevronRight className="w-4 h-4 text-neon" />
                </Link>
              </div>

              <div className="pt-6 border-t border-white/[0.06]">
                <Link
                  href="/pricing"
                  onClick={() => setMenuOpen(false)}
                  className="btn-primary w-full py-3 text-center block"
                >
                  Join Waitlist →
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
