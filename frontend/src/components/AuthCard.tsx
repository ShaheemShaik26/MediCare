import { useState } from 'react'

import { loginUser, registerUser } from '../lib/api'

type Props = {
  onLoggedIn: () => void
}

export function AuthCard({ onLoggedIn }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')

    try {
      if (mode === 'register') {
        await registerUser({ email, password, full_name: name })
      }

      await loginUser({ email, password })
      onLoggedIn()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-card">
      <div className="auth-toggle" role="tablist" aria-label="Account access">
        <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'auth-tab auth-tab-active' : 'auth-tab'} onClick={() => setMode('login')}>
          Sign in
        </button>
        <button type="button" role="tab" aria-selected={mode === 'register'} className={mode === 'register' ? 'auth-tab auth-tab-active' : 'auth-tab'} onClick={() => setMode('register')}>
          Create account
        </button>
      </div>

      <h2>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2>
      <p className="auth-card-description">
        {mode === 'login' ? 'Sign in to your private health space.' : 'Start organizing your health records securely.'}
      </p>

      <form onSubmit={handleSubmit} className="auth-form">
        {mode === 'register' && (
          <div>
            <label className="label" htmlFor="auth-name">Full name</label>
            <input id="auth-name" className="input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
        )}

        <div>
          <label className="label" htmlFor="auth-email">Email address</label>
          <input id="auth-email" className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>

        <div>
          <label className="label" htmlFor="auth-password">Password</label>
          <input id="auth-password" className="input" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>

        {error && <div className="notice notice-error" role="alert">{error}</div>}

        <button className="primary-btn auth-submit" type="submit" disabled={busy}>
          {busy ? 'One moment…' : mode === 'login' ? 'Sign in to your account' : 'Create my account'}
        </button>
      </form>
      <div className="auth-form-footer"><span><ShieldIcon /> Encrypted session</span><span>Private by design</span></div>
    </div>
  )
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  )
}
