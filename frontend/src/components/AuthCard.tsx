import { useState } from 'react'

import { loginUser, registerUser } from '../lib/api'

type Props = {
  onLoggedIn: () => void
}

export function AuthCard({ onLoggedIn }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('demo@medicare.app')
  const [password, setPassword] = useState('StrongPass123!')
  const [name, setName] = useState('Demo User')
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
    <div className="card max-w-xl mx-auto">
      <div className="flex gap-2 mb-4">
        <button type="button" className={mode === 'login' ? 'pill active' : 'pill'} onClick={() => setMode('login')}>
          Log in
        </button>
        <button type="button" className={mode === 'register' ? 'pill active' : 'pill'} onClick={() => setMode('register')}>
          Register
        </button>
      </div>

      <h2 className="text-2xl font-semibold mb-2">Secure access</h2>
      <p className="muted mb-6">Your health records stay private and are scoped to your account.</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        {mode === 'register' && (
          <div>
            <label className="label">Full name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        )}

        <div>
          <label className="label">Email</label>
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>

        <div>
          <label className="label">Password</label>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}

        <button className="primary-btn" type="submit" disabled={busy}>
          {busy ? 'Working...' : mode === 'login' ? 'Log in' : 'Create account'}
        </button>
      </form>
    </div>
  )
}
