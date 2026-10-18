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
      setStatus('Document uploaded successfully.')
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
    <div className="card">
      <h3 className="text-xl font-semibold mb-2">Upload a document</h3>
      <p className="muted mb-4">
        Accepts PDF, PNG, JPEG, TXT, and MD files up to 10 MB. Images and scanned PDF pages use local OCR when available. OCR can misread medical details; review every extracted fact against the original before accepting it.
      </p>

      <label className="primary-btn inline-block cursor-pointer">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.txt,.md,application/pdf,image/png,image/jpeg,text/plain"
          className="hidden"
          onChange={handleUpload}
        />
        {isUploading ? 'Uploading...' : 'Choose file'}
      </label>

      {status && <p className="mt-4 text-sm text-slate-700">{status}</p>}
    </div>
  )
}
