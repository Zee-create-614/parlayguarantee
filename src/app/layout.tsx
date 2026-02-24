import type { Metadata } from 'next'
import { Inter, Space_Grotesk } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const spaceGrotesk = Space_Grotesk({ subsets: ['latin'], variable: '--font-display', weight: ['400', '500', '600', '700'] })

export const metadata: Metadata = {
  title: 'Parlay Guarantee | AI-Powered Sports Picks — NBA, NFL, MLB, NHL, UFC & More',
  description: 'Get AI-generated parlay picks across NBA, NFL, MLB, NHL, UFC, Soccer, College Basketball & Football. Money-back guarantee on every package.',
  keywords: ['sports parlays', 'NBA picks', 'NFL picks', 'MLB picks', 'NHL picks', 'UFC picks', 'soccer picks', 'college basketball', 'college football', 'AI sports betting', 'guaranteed refund', 'parlay picks'],
  openGraph: {
    title: 'Parlay Guarantee — AI Sports Picks with Money-Back Guarantee',
    description: 'Professional AI-generated parlay picks across 8 major sports with full refund protection',
    type: 'website',
    url: 'https://parlayguarantee.com',
    images: [{ url: 'https://parlayguarantee.com/og-image.png', width: 1200, height: 630, alt: 'Parlay Guarantee - AI Sports Picks' }],
    siteName: 'Parlay Guarantee',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Parlay Guarantee — AI Picks for Every Sport',
    description: 'AI-powered picks for NBA, NFL, MLB, NHL, UFC, Soccer & more with money-back guarantee',
    images: ['https://parlayguarantee.com/og-image.png'],
  }
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${spaceGrotesk.variable}`}>
      <head>
        <link rel="icon" href="/favicon.ico" />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "Organization",
              name: "Parlay Guarantee",
              url: "https://parlayguarantee.com",
              logo: "https://parlayguarantee.com/logo.png",
              description: "AI-powered sports parlay picks with money-back guarantee across NBA, NFL, MLB, NHL, UFC, Soccer & more.",
              sameAs: [],
              foundingDate: "2025",
              contactPoint: {
                "@type": "ContactPoint",
                contactType: "customer support",
                url: "https://parlayguarantee.com"
              }
            })
          }}
        />
      </head>
      <body className={`${inter.className} bg-bg-primary text-text-primary min-h-screen antialiased`}>
        <div className="min-h-screen">
          {children}
        </div>
        
        {/* Legal Disclaimer Footer */}
        <div className="bg-bg-secondary/95 border-t border-neon/10 p-3 mt-8">
          <p className="text-xs text-text-muted text-center max-w-6xl mx-auto">
            Not a sportsbook. We sell AI-generated sports analysis for entertainment purposes. 21+ | Gamble Responsibly |{' '}
            <a href="https://www.ncpgambling.org" target="_blank" rel="noopener noreferrer" className="underline hover:text-neon">National Council on Problem Gambling</a>{' '}
            <a href="tel:1-800-522-4700" className="underline hover:text-neon">1-800-522-4700</a> |{' '}
            <a href="/terms" className="underline hover:text-neon">Terms</a> |{' '}
            <a href="/privacy" className="underline hover:text-neon">Privacy</a> |{' '}
            <a href="/responsible-gambling" className="underline hover:text-neon">Responsible Gambling</a>
          </p>
          <p className="text-xs text-text-muted text-center mt-1 opacity-70">
            From the makers of{' '}
            <a href="https://bitcoinintelvault.com" target="_blank" rel="noopener noreferrer" className="underline hover:text-neon">BitcoinIntelVault</a>{' & '}
            <a href="https://debtcrusher.ai" target="_blank" rel="noopener noreferrer" className="underline hover:text-neon">DebtCrusher.ai</a>
          </p>
        </div>
      </body>
    </html>
  )
}
