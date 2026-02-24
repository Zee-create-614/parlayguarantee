import Link from 'next/link'
import { TrendingUp } from 'lucide-react'

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-bg-primary">
      {/* Header */}
      <header className="border-b border-accent-green/20 bg-bg-secondary/50 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <Link href="/" className="flex items-center space-x-2">
              <TrendingUp className="text-accent-green w-8 h-8" />
              <span className="text-2xl font-bold text-gradient">Parlay Guarantee</span>
            </Link>
            <nav className="hidden md:flex space-x-6 items-center">
              <Link href="/pricing" className="hover:text-accent-green transition-colors">Pricing</Link>
              <Link href="/results" className="hover:text-accent-green transition-colors">Results</Link>
              <Link href="/pricing" className="hover:text-accent-green transition-colors">Pricing</Link>
              <Link href="/auth/signin" className="btn-primary text-sm py-2 px-4">Sign In</Link>
            </nav>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-4">Terms of Service</h1>
          <p className="text-text-muted">Last updated: February 15, 2026</p>
        </div>

        <div className="prose prose-lg max-w-none">
          <div className="bg-bg-secondary/30 p-6 rounded-lg border border-accent-green/20 mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">Important Notice</h2>
            <p className="text-text-muted mb-0">
              ParlayGuarantee.com is an <strong>information and entertainment service only</strong>. We do not:
            </p>
            <ul className="text-text-muted mt-3">
              <li>Accept or place bets of any kind</li>
              <li>Operate as a sportsbook or gambling platform</li>
              <li>Provide gambling advice or encourage gambling</li>
              <li>Handle money for betting purposes</li>
            </ul>
          </div>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">1. Service Description</h2>
            <p className="text-text-muted mb-4">
              ParlayGuarantee ("we," "our," or "us") provides sports information, analysis, and parlay suggestions for entertainment and educational purposes. Our artificial intelligence analyzes publicly available sports data to generate parlay combinations across multiple sports including NBA, NFL, MLB, NHL, UFC/MMA, Soccer, College Basketball, and College Football.
            </p>
            <p className="text-text-muted">
              All information provided is for entertainment purposes only and should not be considered gambling advice, recommendations, or encouragement to place bets.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">2. Age and Legal Requirements</h2>
            <p className="text-text-muted mb-4">
              You must be at least 21 years old to use this service. By accessing ParlayGuarantee, you represent and warrant that:
            </p>
            <ul className="text-text-muted mb-4">
              <li>You are at least 21 years of age</li>
              <li>You have the legal capacity to enter into this agreement</li>
              <li>Your use of our service complies with all applicable laws in your jurisdiction</li>
              <li>You understand that sports betting may be illegal in your jurisdiction</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">3. Refund Policy (Our &quot;Guarantee&quot;)</h2>
            <p className="text-text-muted mb-4">
              When we use the word &quot;guarantee&quot; or &quot;money-back promise,&quot; we are referring exclusively to our <strong>refund policy</strong>:
            </p>
            <ul className="text-text-muted mb-4">
              <li>We place a hold (deposit) on your payment method — this is not an immediate charge</li>
              <li>If our picks meet the stated accuracy threshold (e.g., 1+ parlay hit, or 7+ correct straight picks), the deposit is captured as payment for our analysis service</li>
              <li>If our picks do <strong>not</strong> meet the accuracy threshold, the hold is released automatically within 24 hours — you are refunded in full</li>
              <li>Deposit releases are processed back to the original payment method</li>
            </ul>
            <div className="bg-loss-red/10 border border-loss-red/30 rounded-lg p-4 mb-4">
              <p className="text-text-muted text-sm">
                <strong>⚠️ Important:</strong> Our refund policy does <strong>NOT</strong> guarantee that you will profit from sports betting. No sports prediction service can guarantee winning outcomes. All picks are opinions generated by AI models based on statistical analysis. You may lose money wagering on any pick, even picks that meet our accuracy threshold. Users are solely responsible for their own gambling decisions and any resulting financial losses.
              </p>
            </div>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">4. No Gambling Services — Not a Sportsbook</h2>
            <p className="text-text-muted mb-4">
              ParlayGuarantee is an <strong>information and entertainment service</strong> that sells AI-generated sports predictions and opinions. We do not:
            </p>
            <ul className="text-text-muted mb-4">
              <li>Accept, place, or facilitate sports bets or wagers of any kind</li>
              <li>Operate as a bookmaker, sportsbook, or gambling operator</li>
              <li>Hold gambling licenses or permits</li>
              <li>Process gambling transactions</li>
              <li>Partner with, promote, or maintain any affiliation with any sportsbook or gambling platform</li>
            </ul>
            <p className="text-text-muted mb-4">
              <strong>Users are solely responsible for their own gambling decisions.</strong> We are not responsible for any financial losses resulting from wagering on our picks. Our picks are AI-generated opinions based on statistical models — they are not guarantees of any outcome.
            </p>
            <p className="text-text-muted">
              We strongly encourage responsible gambling and recommend users never bet more than they can afford to lose. If you have a gambling problem, please contact the National Council on Problem Gambling at 1-800-522-4700.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">5. Deposit and Payment Terms</h2>
            <h3 className="text-xl font-semibold text-accent-gold mb-3">Deposit Model:</h3>
            <ul className="text-text-muted mb-4">
              <li><strong>Single Deposit:</strong> $50 deposit hold for 10 AI-generated parlay picks across all sports</li>
              <li><strong>No subscriptions:</strong> Each deposit is for one night's picks only</li>
              <li><strong>No recurring charges:</strong> You must manually place a new deposit for future picks</li>
              <li><strong>Deposit capture:</strong> Only occurs when our accuracy threshold is met</li>
              <li><strong>Deposit release:</strong> Automatic within 24 hours when threshold is not met</li>
            </ul>
            <p className="text-text-muted mb-4">
              Deposits are authorized in advance but only captured when the stated accuracy threshold is met. There are no monthly subscriptions or auto-renewals. Each session is independent.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">6. Data Sources and Accuracy</h2>
            <p className="text-text-muted mb-4">
              Our AI analyzes data from publicly available sources including:
            </p>
            <ul className="text-text-muted mb-4">
              <li>Official league statistics and schedules</li>
              <li>Public odds data from major sportsbooks</li>
              <li>Player statistics and injury reports</li>
              <li>Historical performance data</li>
              <li>Weather conditions and other relevant factors</li>
            </ul>
            <p className="text-text-muted">
              While we strive for accuracy, we cannot guarantee that all information is current, complete, or error-free. Sports data changes rapidly, and users should verify information independently.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">7. Prohibited Uses</h2>
            <p className="text-text-muted mb-4">You agree not to:</p>
            <ul className="text-text-muted mb-4">
              <li>Use our service for any illegal purpose</li>
              <li>Share, resell, or redistribute our content without permission</li>
              <li>Attempt to reverse engineer our AI algorithms</li>
              <li>Use automated systems to scrape or harvest our content</li>
              <li>Violate any applicable laws or regulations</li>
              <li>Create multiple accounts to circumvent usage limits</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">8. Intellectual Property</h2>
            <p className="text-text-muted mb-4">
              All content, algorithms, analyses, and intellectual property on ParlayGuarantee are owned by us or our licensors. You may not reproduce, distribute, or create derivative works without written permission.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">9. Disclaimers and Limitations</h2>
            <p className="text-text-muted mb-4">
              <strong>NO WARRANTIES:</strong> Our service is provided "as is" without warranties of any kind. We do not guarantee the accuracy of predictions or that using our service will result in profitable outcomes.
            </p>
            <p className="text-text-muted mb-4">
              <strong>LIMITATION OF LIABILITY:</strong> Our total liability is limited to the amount you paid for the service. We are not liable for any indirect, incidental, or consequential damages.
            </p>
            <p className="text-text-muted">
              <strong>SPORTS BETTING RISKS:</strong> Sports betting involves risk of financial loss. Never bet more than you can afford to lose. If you have a gambling problem, seek help from organizations like the National Council on Problem Gambling (1-800-522-4700).
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">10. Privacy and Data</h2>
            <p className="text-text-muted mb-4">
              We collect and process personal data as described in our <Link href="/privacy" className="text-accent-green hover:underline">Privacy Policy</Link>. By using our service, you consent to our data practices.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">11. Termination</h2>
            <p className="text-text-muted mb-4">
              We may terminate your access at any time for violation of these terms. Since there are no subscriptions to cancel, each deposit transaction is independent. Upon termination, you lose access to paid content, but these terms survive regarding past deposits and usage.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">12. Changes to Terms</h2>
            <p className="text-text-muted mb-4">
              We may update these terms at any time. Material changes will be posted with 30 days notice. Continued use after changes constitutes acceptance.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">13. Contact Information</h2>
            <p className="text-text-muted mb-4">
              For questions about these terms, contact us at:
            </p>
            <p className="text-text-muted">
              Email: legal@parlayguarantee.com<br/>
              Address: [Company Address]<br/>
              Phone: [Support Phone]
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">14. Governing Law</h2>
            <p className="text-text-muted">
              These terms are governed by [State] law. Any disputes will be resolved in [State] courts or through binding arbitration as we elect.
            </p>
          </section>
        </div>

        <div className="mt-12 p-6 bg-loss-red/10 border border-loss-red/30 rounded-lg">
          <h3 className="text-xl font-bold text-loss-red mb-3">⚠️ Responsible Gambling Notice</h3>
          <p className="text-text-muted mb-3">
            Gambling can be addictive and lead to financial problems. If you or someone you know has a gambling problem, help is available:
          </p>
          <ul className="text-text-muted text-sm">
            <li>National Council on Problem Gambling: <strong>1-800-522-4700</strong></li>
            <li>Gamblers Anonymous: <strong>www.gamblersanonymous.org</strong></li>
            <li>National Problem Gambling Helpline: <strong>1-800-522-4700</strong></li>
          </ul>
        </div>

        <div className="mt-8 text-center">
          <Link href="/" className="btn-primary">Back to Home</Link>
        </div>
      </div>
    </div>
  )
}