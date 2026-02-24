'use client'

import { useState, Suspense } from 'react'
import Link from 'next/link'
import { Mail, TrendingUp, CheckCircle, AlertCircle, Loader, User, Phone, MapPin, Calendar } from 'lucide-react'
import { useSearchParams } from 'next/navigation'
import DeviceFingerprint from '../../components/DeviceFingerprint'

const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
  'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
  'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC'
]

const MONTHS = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December'
]

function calculateAge(year: number, month: number, day: number): number {
  const today = new Date()
  const birthDate = new Date(year, month - 1, day)
  let age = today.getFullYear() - birthDate.getFullYear()
  const m = today.getMonth() - birthDate.getMonth()
  if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) age--
  return age
}

function SignInInner() {
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [street, setStreet] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [zip, setZip] = useState('')
  const [dobMonth, setDobMonth] = useState('')
  const [dobDay, setDobDay] = useState('')
  const [dobYear, setDobYear] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'sent' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [ageError, setAgeError] = useState(false)
  const [fingerprint, setFingerprint] = useState('')
  const searchParams = useSearchParams()
  const redirectUrl = searchParams.get('redirect') || ''

  const currentYear = new Date().getFullYear()
  const years = Array.from({ length: 100 }, (_, i) => currentYear - 18 - i)
  const days = Array.from({ length: 31 }, (_, i) => i + 1)

  const formatPhone = (value: string) => {
    const digits = value.replace(/\D/g, '').slice(0, 10)
    if (digits.length <= 3) return digits
    if (digits.length <= 6) return `(${digits.slice(0,3)}) ${digits.slice(3)}`
    return `(${digits.slice(0,3)}) ${digits.slice(3,6)}-${digits.slice(6)}`
  }

  const sendMagicLink = async (e: React.FormEvent) => {
    e.preventDefault()
    setAgeError(false)
    setErrorMessage('')

    // Validate DOB
    const m = parseInt(dobMonth)
    const d = parseInt(dobDay)
    const y = parseInt(dobYear)
    if (!m || !d || !y) {
      setStatus('error')
      setErrorMessage('Please enter your complete date of birth.')
      return
    }
    const age = calculateAge(y, m, d)
    if (age < 21) {
      setAgeError(true)
      setStatus('error')
      setErrorMessage('You must be 21 years or older to use this service.')
      return
    }

    setStatus('loading')

    try {
      const response = await fetch('/api/auth/magic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          fingerprint,
          fullName,
          phone: phone.replace(/\D/g, ''),
          address: { street, city, state, zip },
          dob: `${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`,
          redirect: redirectUrl,
        })
      })

      const data = await response.json()

      if (response.ok) {
        setStatus('sent')
      } else {
        setStatus('error')
        setErrorMessage(data.error || 'Failed to send magic link')
        if (data.ageError) setAgeError(true)
      }
    } catch (error) {
      setStatus('error')
      setErrorMessage('Network error. Please try again.')
    }
  }

  const inputClasses = "w-full px-4 py-3 bg-bg-primary border border-accent-green/20 rounded-lg focus:outline-none focus:border-accent-green transition-colors text-white placeholder-text-muted"
  const selectClasses = "w-full px-4 py-3 bg-bg-primary border border-accent-green/20 rounded-lg focus:outline-none focus:border-accent-green transition-colors text-white appearance-none"

  if (status === 'sent') {
    return (
      <div className="min-h-screen bg-bg-primary flex items-center justify-center px-4">
        <div className="max-w-md w-full">
          <div className="text-center mb-8">
            <Link href="/" className="inline-flex items-center space-x-2 mb-8">
              <TrendingUp className="text-accent-green w-8 h-8" />
              <span className="text-2xl font-bold text-gradient">Parlay Guarantee</span>
            </Link>
          </div>
          
          <div className="card text-center">
            <div className="w-16 h-16 bg-accent-green rounded-full flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-8 h-8 text-black" />
            </div>
            
            <h1 className="text-2xl font-bold mb-4">Check Your Email</h1>
            <p className="text-text-muted mb-6">
              We've sent a magic link to <span className="text-accent-green font-semibold">{email}</span>. 
              Click the link to sign in instantly.
            </p>
            
            <div className="space-y-4">
              <button
                onClick={() => setStatus('idle')}
                className="btn-secondary w-full"
              >
                Send Another Link
              </button>
              
              <Link href="/" className="block text-center text-text-muted hover:text-accent-green transition-colors">
                ← Back to Home
              </Link>
            </div>
          </div>
          
          <div className="mt-6 text-center">
            <p className="text-sm text-text-muted">
              Didn't receive the email? Check your spam folder or try again.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center px-4 py-8">
      <DeviceFingerprint onFingerprint={setFingerprint} />
      <div className="max-w-lg w-full">
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center space-x-2 mb-8">
            <TrendingUp className="text-accent-green w-8 h-8" />
            <span className="text-2xl font-bold text-gradient">Parlay Guarantee</span>
          </Link>
          
          <h1 className="text-3xl font-bold mb-2">Create Your Account</h1>
          <p className="text-text-muted">
            Sign up to access AI-powered parlay picks — first pack is free!
          </p>
        </div>
        
        <div className="card">
          <form onSubmit={sendMagicLink} className="space-y-5">
            {/* Full Name */}
            <div>
              <label htmlFor="fullName" className="block text-sm font-medium mb-2">
                Full Name <span className="text-loss-red">*</span>
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-muted w-5 h-5" />
                <input
                  type="text"
                  id="fullName"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  className={`${inputClasses} pl-12`}
                  placeholder="John Doe"
                />
              </div>
            </div>

            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium mb-2">
                Email Address <span className="text-loss-red">*</span>
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-muted w-5 h-5" />
                <input
                  type="email"
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className={`${inputClasses} pl-12`}
                  placeholder="your@email.com"
                />
              </div>
            </div>

            {/* Phone */}
            <div>
              <label htmlFor="phone" className="block text-sm font-medium mb-2">
                Phone Number <span className="text-loss-red">*</span>
              </label>
              <div className="relative">
                <Phone className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-muted w-5 h-5" />
                <input
                  type="tel"
                  id="phone"
                  value={phone}
                  onChange={(e) => setPhone(formatPhone(e.target.value))}
                  required
                  className={`${inputClasses} pl-12`}
                  placeholder="(555) 123-4567"
                />
              </div>
            </div>

            {/* Date of Birth */}
            <div>
              <label className="block text-sm font-medium mb-2">
                <span className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-text-muted" />
                  Date of Birth <span className="text-loss-red">*</span>
                </span>
              </label>
              <div className="grid grid-cols-3 gap-3">
                <select
                  value={dobMonth}
                  onChange={(e) => setDobMonth(e.target.value)}
                  required
                  className={selectClasses}
                >
                  <option value="">Month</option>
                  {MONTHS.map((m, i) => (
                    <option key={m} value={i + 1}>{m}</option>
                  ))}
                </select>
                <select
                  value={dobDay}
                  onChange={(e) => setDobDay(e.target.value)}
                  required
                  className={selectClasses}
                >
                  <option value="">Day</option>
                  {days.map(d => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
                <select
                  value={dobYear}
                  onChange={(e) => setDobYear(e.target.value)}
                  required
                  className={selectClasses}
                >
                  <option value="">Year</option>
                  {years.map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-text-muted mt-1">You must be 21 or older to use this service.</p>
            </div>

            {/* Address */}
            <div>
              <label className="block text-sm font-medium mb-2">
                <span className="flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-text-muted" />
                  Address <span className="text-loss-red">*</span>
                </span>
              </label>
              <div className="space-y-3">
                <input
                  type="text"
                  value={street}
                  onChange={(e) => setStreet(e.target.value)}
                  required
                  className={inputClasses}
                  placeholder="Street Address"
                />
                <div className="grid grid-cols-5 gap-3">
                  <input
                    type="text"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    required
                    className={`${inputClasses} col-span-2`}
                    placeholder="City"
                  />
                  <select
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    required
                    className={`${selectClasses} col-span-1`}
                  >
                    <option value="">State</option>
                    {US_STATES.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={zip}
                    onChange={(e) => setZip(e.target.value.replace(/\D/g, '').slice(0, 5))}
                    required
                    pattern="[0-9]{5}"
                    className={`${inputClasses} col-span-2`}
                    placeholder="ZIP Code"
                  />
                </div>
              </div>
            </div>

            {/* Age Error */}
            {ageError && (
              <div className="flex items-center p-4 bg-loss-red/20 border-2 border-loss-red rounded-lg">
                <AlertCircle className="w-6 h-6 text-loss-red mr-3 flex-shrink-0" />
                <div>
                  <p className="font-bold text-loss-red">Age Restriction</p>
                  <p className="text-sm text-loss-red">You must be 21 years or older to use this service.</p>
                </div>
              </div>
            )}
            
            {/* General Error */}
            {status === 'error' && !ageError && (
              <div className="flex items-center p-3 bg-loss-red/10 border border-loss-red/30 rounded-lg">
                <AlertCircle className="w-5 h-5 text-loss-red mr-2 flex-shrink-0" />
                <span className="text-sm text-loss-red">{errorMessage}</span>
              </div>
            )}
            
            <button
              type="submit"
              disabled={status === 'loading' || !email || !fullName || !phone || !street || !city || !state || !zip || !dobMonth || !dobDay || !dobYear}
              className="btn-primary w-full flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {status === 'loading' ? (
                <>
                  <Loader className="w-5 h-5 mr-2 animate-spin" />
                  Sending Magic Link...
                </>
              ) : (
                'Sign Up & Get Free Pack →'
              )}
            </button>
          </form>
          
          <div className="mt-6 pt-6 border-t border-accent-green/20">
            <p className="text-sm text-text-muted text-center">
              Already have an account? Enter your email above — we'll recognize you.
            </p>
          </div>
        </div>
        
        <div className="mt-8 text-center space-y-2">
          <p className="text-sm text-text-muted">
            🔒 Secure magic link authentication — No passwords needed
          </p>
          <p className="text-sm text-text-muted">
            Links expire in 15 minutes for your security
          </p>
        </div>
        
        {/* Benefits reminder */}
        <div className="mt-8 card">
          <h3 className="font-bold mb-4 text-center">Why Sign Up?</h3>
          <ul className="space-y-2 text-sm">
            <li className="flex items-center">
              <CheckCircle className="w-4 h-4 text-accent-green mr-2 flex-shrink-0" />
              🎁 First full pack completely FREE
            </li>
            <li className="flex items-center">
              <CheckCircle className="w-4 h-4 text-accent-green mr-2 flex-shrink-0" />
              Access daily 5-leg and 7-leg parlay picks
            </li>
            <li className="flex items-center">
              <CheckCircle className="w-4 h-4 text-accent-green mr-2 flex-shrink-0" />
              Copy-to-clipboard functionality
            </li>
            <li className="flex items-center">
              <CheckCircle className="w-4 h-4 text-accent-green mr-2 flex-shrink-0" />
              Track your purchase history
            </li>
            <li className="flex items-center">
              <CheckCircle className="w-4 h-4 text-accent-green mr-2 flex-shrink-0" />
              Automatic refund processing
            </li>
          </ul>
        </div>
        
        <div className="mt-8 text-center">
          <Link href="/" className="text-text-muted hover:text-accent-green transition-colors">
            ← Back to Home
          </Link>
        </div>
      </div>
    </div>
  )
}

export default function SignInPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-bg-primary flex items-center justify-center"><div className="text-white">Loading...</div></div>}>
      <SignInInner />
    </Suspense>
  )
}
