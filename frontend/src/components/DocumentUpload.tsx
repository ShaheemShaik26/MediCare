import { useRef, useState } from 'react'

import { uploadDocument } from '../lib/api'

type Props = {
  onUploaded: () => void
}

export function DocumentUpload({ onUploaded }: Props) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [status, setStatus] = useState('')
  const [isUploading, setIsUploading] = useState(false)

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    setIsUploading(true)
    setStatus('Uploading and extracting document...')

    try {
      await uploadDocument(file)
      setStatus('Document uploaded. Extracted details now appear on your timeline, where you can edit or dismiss them.')
      onUploaded()
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  return (
    <div className="upload-widget">
      <input
        ref={fileInputRef}
        id="health-record-upload"
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.txt,.md,application/pdf,image/png,image/jpeg,text/plain"
        className="visually-hidden"
        onChange={handleUpload}
        disabled={isUploading}
      />
      <div className="upload-widget-copy">
        <span className="upload-file-icon"><FileIcon /></span>
        <span>
          <strong>Choose a file to upload</strong>
          <small>PDF, PNG, JPEG, TXT, or MD · up to 10 MB</small>
        </span>
      </div>
      <label className={`primary-btn upload-button${isUploading ? ' button-disabled' : ''}`} htmlFor="health-record-upload">
        {isUploading ? 'Uploading…' : 'Browse files'}
      </label>
      {status && <p className="upload-status" role="status">{status}</p>}
      <p className="upload-privacy-note">
        Scanned pages may use local OCR. Always check extracted details against the original before accepting.
      </p>
    </div>
  )
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M8 13h8M8 17h8" />
    </svg>
  )
}
