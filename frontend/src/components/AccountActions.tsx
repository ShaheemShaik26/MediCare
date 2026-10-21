import { useState } from 'react'
import { ArrowDownToLine, AlertTriangle } from 'lucide-react'

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
    <section className="panel account-actions" aria-labelledby="account-actions-heading">
      <div className="panel-heading">
        <div><h2 id="account-actions-heading">Data controls</h2><p>Take a copy or remove your data.</p></div>
      </div>
      <button className="secondary-btn export-button" type="button" onClick={() => void handleExport()} disabled={busy}>
        <ArrowDownToLine size={17} /> {busy ? 'Preparing…' : 'Export my data'}
      </button>

      <form className="delete-account-form" onSubmit={(event) => void handleDelete(event)}>
        <div className="danger-heading"><AlertTriangle size={17} /><h3>Delete account</h3></div>
        <p>This permanently removes your account, health facts, and uploaded files.</p>
        <label className="label" htmlFor="delete-account-password">Confirm with your password</label>
        <input id="delete-account-password" className="input" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        <button className="danger-button" type="submit" disabled={busy || !password}>
          Permanently delete account
        </button>
      </form>

      {message && <p className="mt-4 text-sm muted" role="status">{message}</p>}
      {error && <p className="mt-4 text-sm text-red-600" role="alert">{error}</p>}
    </section>
  )
}
