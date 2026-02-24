import Link from 'next/link'
import { TrendingUp, Shield, Eye, Lock, Database } from 'lucide-react'

export default function PrivacyPage() {
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
          <h1 className="text-4xl font-bold mb-4 flex items-center gap-3">
            <Shield className="text-accent-green w-10 h-10" />
            Privacy Policy
          </h1>
          <p className="text-text-muted">Last updated: February 15, 2026</p>
        </div>

        <div className="bg-bg-secondary/30 p-6 rounded-lg border border-accent-green/20 mb-8">
          <h2 className="text-2xl font-bold text-accent-green mb-4 flex items-center gap-2">
            <Eye className="w-6 h-6" />
            Privacy at a Glance
          </h2>
          <div className="grid md:grid-cols-3 gap-4 text-center">
            <div>
              <Lock className="w-8 h-8 text-accent-gold mx-auto mb-2" />
              <h3 className="font-bold text-accent-gold">Data Security</h3>
              <p className="text-sm text-text-muted">Enterprise-grade encryption for all data</p>
            </div>
            <div>
              <Database className="w-8 h-8 text-accent-gold mx-auto mb-2" />
              <h3 className="font-bold text-accent-gold">Minimal Collection</h3>
              <p className="text-sm text-text-muted">We only collect what's necessary</p>
            </div>
            <div>
              <Shield className="w-8 h-8 text-accent-gold mx-auto mb-2" />
              <h3 className="font-bold text-accent-gold">No Sale</h3>
              <p className="text-sm text-text-muted">We never sell your personal data</p>
            </div>
          </div>
        </div>

        <div className="prose prose-lg max-w-none">
          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">1. Introduction</h2>
            <p className="text-text-muted mb-4">
              ParlayGuarantee ("we," "our," or "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our sports information service at parlayguarantee.com (the "Service").
            </p>
            <p className="text-text-muted">
              By using our Service, you consent to the data practices described in this policy. If you do not agree with this policy, please do not use our Service.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">2. Information We Collect</h2>
            
            <h3 className="text-xl font-semibold text-accent-gold mb-3">Information You Provide</h3>
            <ul className="text-text-muted mb-4">
              <li><strong>Account Information:</strong> Email address for account creation and magic link authentication</li>
              <li><strong>Payment Information:</strong> Billing details processed securely through our payment processors</li>
              <li><strong>Communication:</strong> Messages you send us through support channels</li>
              <li><strong>Preferences:</strong> Sport preferences, notification settings, and service preferences</li>
              <li><strong>Betting Configuration:</strong> Preferred sportsbook platform and typical bet amounts, used solely for tracking accuracy threshold fulfillment and processing refunds</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">Information Automatically Collected</h3>
            <ul className="text-text-muted mb-4">
              <li><strong>Usage Data:</strong> Pages viewed, time spent, features used, clicks and interactions</li>
              <li><strong>Device Information:</strong> Browser type, operating system, device type, screen resolution</li>
              <li><strong>IP Address:</strong> For security, fraud prevention, and approximate location</li>
              <li><strong>Cookies:</strong> Session management and user preferences (see Cookie section)</li>
              <li><strong>Log Data:</strong> Server logs including IP addresses, timestamps, and requested resources</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">Information We Do NOT Collect</h3>
            <ul className="text-text-muted mb-4">
              <li>Social Security Numbers or government ID numbers</li>
              <li>Banking account information (payment processors handle this)</li>
              <li>Precise location data (unless you explicitly provide it)</li>
              <li>Audio or video recordings</li>
              <li>Biometric data</li>
              <li>Information about your actual bets or gambling activities</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">3. How We Use Your Information</h2>
            
            <h3 className="text-xl font-semibold text-accent-gold mb-3">Service Provision</h3>
            <ul className="text-text-muted mb-4">
              <li>Deliver sports information and parlay suggestions</li>
              <li>Process payments and manage subscriptions</li>
              <li>Send magic link authentication emails</li>
              <li>Provide customer support</li>
              <li>Customize content based on your sport preferences</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">Business Operations</h3>
            <ul className="text-text-muted mb-4">
              <li>Improve and optimize our AI algorithms</li>
              <li>Analyze usage patterns to enhance user experience</li>
              <li>Prevent fraud and maintain security</li>
              <li>Comply with legal obligations</li>
              <li>Conduct internal research and analytics</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">Communications</h3>
            <ul className="text-text-muted mb-4">
              <li>Send service-related notifications</li>
              <li>Provide customer support responses</li>
              <li>Send optional marketing emails (with your consent)</li>
              <li>Notify about important policy or service changes</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">4. Information Sharing and Disclosure</h2>
            
            <h3 className="text-xl font-semibold text-accent-gold mb-3">We Share Information With:</h3>
            <ul className="text-text-muted mb-4">
              <li><strong>Service Providers:</strong> Payment processors, email services, cloud hosting, analytics providers</li>
              <li><strong>Legal Requirements:</strong> When required by law, legal process, or government request</li>
              <li><strong>Business Transfers:</strong> In connection with mergers, acquisitions, or asset sales</li>
              <li><strong>Consent:</strong> When you explicitly authorize us to share specific information</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">We DO NOT:</h3>
            <ul className="text-text-muted mb-4">
              <li>Sell your personal information to third parties</li>
              <li>Share your data with advertising networks for targeted ads</li>
              <li>Provide your information to gambling operators or sportsbooks</li>
              <li>Share user data with other users or make it publicly visible</li>
              <li>Use your data for purposes other than those described in this policy</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">5. Cookies and Tracking Technologies</h2>
            
            <h3 className="text-xl font-semibold text-accent-gold mb-3">Essential Cookies</h3>
            <p className="text-text-muted mb-3">Required for basic site functionality:</p>
            <ul className="text-text-muted mb-4">
              <li>Authentication and session management</li>
              <li>Security and fraud prevention</li>
              <li>Load balancing and performance</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">Analytics Cookies</h3>
            <p className="text-text-muted mb-3">Help us understand how you use our service:</p>
            <ul className="text-text-muted mb-4">
              <li>Page views and user interactions</li>
              <li>Performance metrics and error tracking</li>
              <li>Feature usage and user journey analysis</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">Cookie Management</h3>
            <p className="text-text-muted mb-4">
              You can control cookies through your browser settings. However, disabling essential cookies may affect site functionality. We do not use third-party advertising cookies or tracking pixels.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">6. Data Security</h2>
            <p className="text-text-muted mb-4">We implement industry-standard security measures:</p>
            
            <h3 className="text-xl font-semibold text-accent-gold mb-3">Technical Safeguards</h3>
            <ul className="text-text-muted mb-4">
              <li><strong>Encryption:</strong> All data in transit and at rest is encrypted using AES-256</li>
              <li><strong>Secure Authentication:</strong> Magic link system eliminates password vulnerabilities</li>
              <li><strong>HTTPS:</strong> All connections use SSL/TLS encryption</li>
              <li><strong>Secure Hosting:</strong> Enterprise-grade cloud infrastructure with 24/7 monitoring</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">Operational Security</h3>
            <ul className="text-text-muted mb-4">
              <li>Regular security audits and vulnerability assessments</li>
              <li>Access controls and employee background checks</li>
              <li>Incident response procedures</li>
              <li>Regular backups and disaster recovery plans</li>
            </ul>

            <p className="text-text-muted">
              While we use industry-standard security measures, no system is 100% secure. We encourage users to use unique, strong credentials and report any suspicious activity immediately.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">7. Your Privacy Rights</h2>
            
            <h3 className="text-xl font-semibold text-accent-gold mb-3">Access and Control</h3>
            <ul className="text-text-muted mb-4">
              <li><strong>Access:</strong> Request a copy of your personal data</li>
              <li><strong>Rectification:</strong> Correct inaccurate or incomplete data</li>
              <li><strong>Deletion:</strong> Request deletion of your personal data</li>
              <li><strong>Portability:</strong> Receive your data in a machine-readable format</li>
              <li><strong>Objection:</strong> Object to certain data processing activities</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">California Privacy Rights (CCPA)</h3>
            <p className="text-text-muted mb-3">If you are a California resident, you have additional rights:</p>
            <ul className="text-text-muted mb-4">
              <li>Right to know what personal information is collected</li>
              <li>Right to know if personal information is sold or disclosed</li>
              <li>Right to opt-out of the sale of personal information</li>
              <li>Right to delete personal information</li>
              <li>Right to non-discrimination for exercising privacy rights</li>
            </ul>

            <h3 className="text-xl font-semibold text-accent-gold mb-3">European Privacy Rights (GDPR)</h3>
            <p className="text-text-muted mb-4">
              If you are in the EU/EEA, you have rights under GDPR including access, rectification, erasure, restriction, portability, and objection. You also have the right to lodge a complaint with your data protection authority.
            </p>

            <p className="text-text-muted">
              To exercise any of these rights, contact us at privacy@parlayguarantee.com. We will respond within the legally required timeframe.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">8. Data Retention</h2>
            <p className="text-text-muted mb-4">We retain personal information only as long as necessary:</p>
            <ul className="text-text-muted mb-4">
              <li><strong>Account Data:</strong> Until account deletion or 3 years after last activity</li>
              <li><strong>Payment Records:</strong> 7 years for tax and accounting purposes</li>
              <li><strong>Usage Analytics:</strong> Aggregated data may be retained indefinitely</li>
              <li><strong>Support Communications:</strong> 2 years after resolution</li>
              <li><strong>Marketing Data:</strong> Until you unsubscribe or request deletion</li>
            </ul>
            <p className="text-text-muted">
              When we delete data, it is removed from our active systems. Some data may persist in backups for up to 90 days before permanent deletion.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">9. International Data Transfers</h2>
            <p className="text-text-muted mb-4">
              Our services are based in the United States. If you access our Service from outside the US, your data may be transferred to, stored, and processed in the US where our servers are located and our service providers operate.
            </p>
            <p className="text-text-muted">
              We ensure appropriate safeguards are in place for international transfers, including standard contractual clauses and adequacy decisions where applicable.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">10. Children's Privacy</h2>
            <p className="text-text-muted mb-4">
              Our Service is not intended for individuals under 21 years of age. We do not knowingly collect personal information from anyone under 21. If we learn we have collected information from someone under 21, we will delete that information immediately.
            </p>
            <p className="text-text-muted">
              If you believe we have collected information from someone under 21, please contact us at privacy@parlayguarantee.com.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">11. Changes to This Privacy Policy</h2>
            <p className="text-text-muted mb-4">
              We may update this Privacy Policy from time to time. We will notify you of any material changes by:
            </p>
            <ul className="text-text-muted mb-4">
              <li>Posting the updated policy on our website</li>
              <li>Sending email notification to registered users</li>
              <li>Displaying a notice on our Service</li>
            </ul>
            <p className="text-text-muted">
              Material changes will be effective 30 days after notice is provided. Your continued use of the Service after the effective date constitutes acceptance of the updated policy.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-bold text-accent-green mb-4">12. Contact Us</h2>
            <p className="text-text-muted mb-4">
              If you have questions about this Privacy Policy or our data practices, contact us:
            </p>
            <div className="bg-bg-secondary/30 p-4 rounded-lg border border-accent-green/20">
              <p className="text-text-muted mb-2">
                <strong>Email:</strong> privacy@parlayguarantee.com
              </p>
              <p className="text-text-muted mb-2">
                <strong>Data Protection Officer:</strong> dpo@parlayguarantee.com
              </p>
              <p className="text-text-muted mb-2">
                <strong>Mailing Address:</strong><br/>
                ParlayGuarantee Privacy Team<br/>
                [Company Address]<br/>
                [City, State ZIP]
              </p>
              <p className="text-text-muted">
                <strong>Phone:</strong> [Support Phone]
              </p>
            </div>
          </section>
        </div>

        <div className="mt-8 text-center">
          <Link href="/" className="btn-primary mr-4">Back to Home</Link>
          <Link href="/terms" className="btn-secondary">View Terms of Service</Link>
        </div>
      </div>
    </div>
  )
}