import { useMemo, useState } from 'react'

import { downloadDocument, reviewFact } from '../lib/api'
import type { DocumentRecord, MedicalFact } from '../types'

type Props = {
  documents: DocumentRecord[]
  timeline: MedicalFact[]
  onReviewed: () => void
}

export function HealthTimeline({ documents, timeline, onReviewed }: Props) {
  const totalAccepted = useMemo(() => timeline.length, [timeline])
  const [downloadError, setDownloadError] = useState('')

  const handleReview = async (factId: number, status: 'accepted' | 'rejected') => {
    await reviewFact(factId, status)
    onReviewed()
  }

  const handleDownload = async (documentId: number, fileName: string) => {
    setDownloadError('')
    try {
      await downloadDocument(documentId, fileName)
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'Unable to download this document')
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <div className="card">
          <div className="muted">Documents uploaded</div>
          <div className="text-3xl font-bold mt-2">{documents.length}</div>
        </div>
        <div className="card">
          <div className="muted">Accepted facts</div>
          <div className="text-3xl font-bold mt-2">{totalAccepted}</div>
        </div>
        <div className="card">
          <div className="muted">Review status</div>
          <div className="text-3xl font-bold mt-2">Active</div>
        </div>
      </div>

      <div className="card">
        <h3 className="text-xl font-semibold mb-4">Documents</h3>
        {downloadError && <p className="text-sm text-red-600 mb-4" role="alert">{downloadError}</p>}
        {documents.length === 0 ? <p className="muted">No uploads yet.</p> : (
          <ul className="space-y-3">
            {documents.map((document) => (
              <li key={document.id} className="border border-slate-200 rounded-xl p-3">
                <div className="flex justify-between gap-4">
                  <div>
                    <p className="font-medium">{document.file_name}</p>
                    <p className="text-xs muted">{new Date(document.uploaded_at).toLocaleString()}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="badge">{document.status.replace('_', ' ')}</span>
                    <button
                      className="secondary-btn"
                      type="button"
                      onClick={() => void handleDownload(document.id, document.file_name)}
                    >
                      Download original
                    </button>
                  </div>
                </div>
                {document.status === 'manual_review' && (
                  <p className="mt-3 text-sm muted" role="status">
                    No text could be extracted. No facts were inferred; review the original document manually.
                  </p>
                )}
                {document.status === 'ocr_review' && (
                  <p className="mt-3 text-sm muted" role="status">
                    Some text was read using OCR. OCR can misread medical details; compare each extracted fact with the original before accepting it.
                  </p>
                )}
                <div className="mt-3 text-xs muted">
                  {document.document_type && <span>Type: {document.document_type}</span>}
                  {document.document_date && <span className="ml-3">Date: {document.document_date}</span>}
                  {document.provider_name && <span className="ml-3">Provider: {document.provider_name}</span>}
                </div>
                {document.preview_text && (
                  <p className="mt-3 text-sm text-slate-700 whitespace-pre-wrap">{document.preview_text.slice(0, 240)}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h3 className="text-xl font-semibold mb-4">Longitudinal timeline</h3>
        {timeline.length === 0 ? <p className="muted">No accepted facts yet. Upload a document and review the extracted items.</p> : (
          <ul className="space-y-4">
            {timeline.map((fact) => (
              <li key={fact.id} className="border border-slate-200 rounded-xl p-4">
                <div className="flex justify-between gap-3">
                  <div>
                    <p className="font-semibold capitalize">{fact.fact_type}</p>
                    <p className="text-sm text-slate-700">{fact.value}</p>
                    {fact.source_excerpt && <p className="mt-2 text-xs muted">Evidence: {fact.source_excerpt}</p>}
                  </div>
                  <div className="flex gap-2">
                    <button className="secondary-btn" onClick={() => handleReview(fact.id, 'rejected')}>
                      Reject
                    </button>
                    <button className="primary-btn" onClick={() => handleReview(fact.id, 'accepted')}>
                      Accept
                    </button>
                  </div>
                </div>
                <p className="mt-3 text-xs muted">
                  Confidence: {fact.confidence.toFixed(2)}
                  {fact.page_number !== null && fact.page_number !== undefined && ` | Page: ${fact.page_number}`}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
