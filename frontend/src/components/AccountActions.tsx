import { useState } from 'react'

import { deleteAccount, downloadAccountExport } from '../lib/api'

type Props = {
  onDeleted: () => void
}

export function AccountActions({ onDeleted }: Props) {
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const handleExport = async () => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await downloadAccountExport()
      setMessage('Your account export has been downloaded.')
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : 'Could not export account data')
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!window.confirm('Permanently delete your account, medical records, and uploaded documents? This cannot be undone.')) {
      return
    }

    setBusy(true)
    setError('')
    setMessage('')
    try {
      await deleteAccount(password)
      onDeleted()
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Could not delete account')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card" aria-labelledby="account-actions-heading">
      <h2 id="account-actions-heading" className="text-xl font-semibold mb-2">Account data</h2>
      <p className="muted mb-4">Export a copy of your records and uploaded files, or permanently delete your account data.</p>
      <button className="secondary-btn" type="button" onClick={() => void handleExport()} disabled={busy}>
        Download my data
      </button>

      <form className="mt-6 space-y-4" onSubmit={(event) => void handleDelete(event)}>
        <h3 className="font-semibold text-red-600">Delete account</h3>
        <p className="text-sm muted">This permanently removes your account, health facts, and uploaded documents. Enter your password to confirm.</p>
        <label className="label" htmlFor="delete-account-password">Current password</label>
        <input
          id="delete-account-password"
          className="input"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        <button className="secondary-btn" type="submit" disabled={busy || !password}>
          Permanently delete my account
        </button>
      </form>

      {message && <p className="mt-4 text-sm muted" role="status">{message}</p>}
      {error && <p className="mt-4 text-sm text-red-600" role="alert">{error}</p>}
    </section>
  )
}
