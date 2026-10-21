import { useState, type FormEvent } from 'react'
import { Check, Eye, FileText, Pencil, Plus, X } from 'lucide-react'

import { createManualFact, reviewFact, viewDocument } from '../lib/api'
import type { DocumentRecord, ManualFactType, MedicalFact } from '../types'

const manualFactTypes: { value: ManualFactType; label: string }[] = [
  { value: 'diagnosis', label: 'Diagnosis' },
  { value: 'symptom', label: 'Symptom' },
  { value: 'medication', label: 'Medication' },
  { value: 'allergy', label: 'Allergy' },
  { value: 'lab', label: 'Test or measurement' },
  { value: 'procedure', label: 'Procedure' },
  { value: 'medical_event', label: 'Medical event' },
  { value: 'provider', label: 'Provider' },
  { value: 'lifestyle_activity', label: 'Lifestyle: activity' },
  { value: 'lifestyle_sleep', label: 'Lifestyle: sleep' },
  { value: 'lifestyle_diet', label: 'Lifestyle: diet' },
  { value: 'lifestyle_tobacco', label: 'Lifestyle: tobacco' },
  { value: 'lifestyle_alcohol', label: 'Lifestyle: alcohol' },
]

type Props = {
  facts: MedicalFact[]
  documents: DocumentRecord[]
  noFactsDetected: boolean
  onReviewed: () => void
}

export function ReviewQueue({ facts, documents, noFactsDetected, onReviewed }: Props) {
  const [busyFact, setBusyFact] = useState<number | null>(null)
  const [editingFact, setEditingFact] = useState<number | null>(null)
  const [draft, setDraft] = useState({ factType: '', value: '', eventDate: '' })
  const [manualDocumentId, setManualDocumentId] = useState<number | null>(documents[0]?.id ?? null)
  const [manualFactType, setManualFactType] = useState<ManualFactType>('lab')
  const [manualValue, setManualValue] = useState('')
  const [manualEventDate, setManualEventDate] = useState('')
  const [manualPageNumber, setManualPageNumber] = useState('')
  const [manualBusy, setManualBusy] = useState(false)
  const [manualError, setManualError] = useState('')
  const [manualFormOpen, setManualFormOpen] = useState(false)
  const [error, setError] = useState('')
  const [viewError, setViewError] = useState('')

  const handleViewDocument = async (documentId: number) => {
    setViewError('')
    try {
      await viewDocument(documentId)
    } catch (viewError) {
      setViewError(viewError instanceof Error ? viewError.message : 'Unable to open this document')
    }
  }

  const handleReview = async (fact: MedicalFact, status: 'accepted' | 'rejected') => {
    const isEditing = editingFact === fact.id && status === 'accepted'
    if (isEditing && (!draft.factType.trim() || !draft.value.trim())) {
      setError('Enter both a detail type and value before accepting this fact.')
      return
    }
    setBusyFact(fact.id)
    setError('')
    try {
      await reviewFact(fact.id, {
        status,
        ...(isEditing ? {
          fact_type: draft.factType.trim(),
          value: draft.value.trim(),
          event_date: draft.eventDate || null,
          clear_event_date: !draft.eventDate,
        } : {}),
      })
      setEditingFact(null)
      onReviewed()
    } catch (reviewError) {
      setError(reviewError instanceof Error ? reviewError.message : 'Could not update this fact')
    } finally {
      setBusyFact(null)
    }
  }

  const handleManualFactSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (manualDocumentId === null || !manualValue.trim()) {
      setManualError('Choose a source document and enter a detail.')
      return
    }
    setManualBusy(true)
    setManualError('')
    try {
      await createManualFact(manualDocumentId, {
        fact_type: manualFactType,
        value: manualValue.trim(),
        event_date: manualEventDate || null,
        page_number: manualPageNumber ? Number(manualPageNumber) : null,
      })
      setManualValue('')
      setManualEventDate('')
      setManualPageNumber('')
      setManualFormOpen(false)
      onReviewed()
    } catch (manualSubmitError) {
      setManualError(manualSubmitError instanceof Error ? manualSubmitError.message : 'Could not add this detail')
    } finally {
      setManualBusy(false)
    }
  }

  if (error) {
    return <div className="notice notice-error" role="alert">{error}</div>
  }

  if (!facts.length) {
    if (noFactsDetected) {
      return (
        <div className="review-empty">
          <span className="review-empty-icon"><FileText size={17} /></span>
          <div className="review-empty-copy">
            <strong>No details were detected to review</strong>
            <small>No extracted details are available yet. Try extracting the existing file again or open the original document and add details manually.</small>
            {viewError && <span className="notice notice-error" role="alert">{viewError}</span>}
            <div className="review-document-links">
              {documents.map((document) => (
                <span className="review-document-link-group" key={document.id}>
                  <button
                    className="secondary-btn"
                    type="button"
                    onClick={() => void handleViewDocument(document.id)}
                  >
                    <Eye size={16} /> View {document.file_name}
                  </button>
                  <button
                    className="text-link"
                    type="button"
                    onClick={() => {
                      setManualDocumentId(document.id)
                      setManualFormOpen(true)
                      setManualError('')
                    }}
                  >
                    <Plus size={15} /> Add a detail
                  </button>
                </span>
              ))}
            </div>
            {manualFormOpen && (
              <form className="manual-fact-form" onSubmit={(event) => void handleManualFactSubmit(event)}>
                <h3>Add a detail from the original</h3>
                <p>This detail will appear on your timeline as unconfirmed. You can edit, confirm, or dismiss it.</p>
                <label>
                  <span>Source document</span>
                  <select
                    value={manualDocumentId ?? ''}
                    onChange={(event) => setManualDocumentId(Number(event.target.value))}
                  >
                    {documents.map((document) => <option key={document.id} value={document.id}>{document.file_name}</option>)}
                  </select>
                </label>
                <label>
                  <span>Detail type</span>
                  <select
                    value={manualFactType}
                    onChange={(event) => {
                      const selectedType = manualFactTypes.find((item) => item.value === event.target.value)
                      if (selectedType) setManualFactType(selectedType.value)
                    }}
                  >
                    {manualFactTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </label>
                <label>
                  <span>Detail exactly as recorded</span>
                  <textarea
                    value={manualValue}
                    onChange={(event) => setManualValue(event.target.value)}
                    maxLength={2000}
                    rows={3}
                    required
                  />
                </label>
                <div className="manual-fact-fields">
                  <label>
                    <span>Event date (only if stated)</span>
                    <input type="date" value={manualEventDate} onChange={(event) => setManualEventDate(event.target.value)} />
                  </label>
                  <label>
                    <span>Page number</span>
                    <input
                      type="number"
                      min="1"
                      max="100"
                      value={manualPageNumber}
                      onChange={(event) => setManualPageNumber(event.target.value)}
                    />
                  </label>
                </div>
                {manualError && <span className="notice notice-error" role="alert">{manualError}</span>}
                <div className="manual-fact-actions">
                  <button className="secondary-btn" type="button" onClick={() => setManualFormOpen(false)}>Cancel</button>
                  <button className="primary-btn" type="submit" disabled={manualBusy}>
                    {manualBusy ? 'Saving…' : 'Save for my review'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )
    }

    return (
      <div className="review-empty">
        <span className="review-empty-icon"><Check size={18} /></span>
        <span>
          <strong>You’re all caught up</strong>
          <small>New details from your documents will wait here for your review.</small>
        </span>
      </div>
    )
  }

  return (
    <ul className="review-list">
      {facts.map((fact) => {
        const document = documents.find((item) => item.id === fact.document_id)
        const isOcr = fact.source_excerpt?.startsWith('OCR text:') || fact.source_excerpt?.startsWith('OCR + AI suggestion:')
        const isAi = fact.source_excerpt?.includes('AI suggestion:') ?? false
        const evidenceText = fact.source_excerpt?.replace(/^(?:OCR text|OCR \+ AI suggestion|AI suggestion):\s*/, '')
        const isEditing = editingFact === fact.id
        return (
          <li className="review-item" key={fact.id}>
            <span className="review-fact-icon"><FileText size={17} /></span>
            <div className="review-fact-content">
              <div className="review-fact-meta">
                <span className="fact-type">
                  {fact.fact_type.replace(/^lifestyle_/, '').replace(/_/g, ' ').replace(/^\w/, (letter) => letter.toUpperCase())}
                </span>
                {isOcr && <span className="ocr-label">OCR extracted</span>}
                {isAi && <span className="ai-label">AI suggestion · verify</span>}
              </div>
              {isEditing ? (
                <div className="review-edit-fields">
                  <label>
                    <span>Detail type</span>
                    <input
                      value={draft.factType}
                      maxLength={64}
                      onChange={(event) => setDraft((current) => ({ ...current, factType: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Extracted detail</span>
                    <textarea
                      value={draft.value}
                      maxLength={2000}
                      rows={3}
                      onChange={(event) => setDraft((current) => ({ ...current, value: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>Clinical event date (only if stated)</span>
                    <input
                      type="date"
                      value={draft.eventDate}
                      onChange={(event) => setDraft((current) => ({ ...current, eventDate: event.target.value }))}
                    />
                  </label>
                </div>
              ) : (
                <>
                  <strong className="review-fact-value">{fact.value}</strong>
                  {(fact.event_date || fact.numeric_value !== null && fact.numeric_value !== undefined) && (
                    <span className="review-source">
                      {fact.event_date ? `Event date: ${fact.event_date}` : ''}
                      {fact.numeric_value !== null && fact.numeric_value !== undefined
                        ? ` · Parsed measurement: ${fact.numeric_value}${fact.unit ? ` ${fact.unit}` : ''}`
                        : ''}
                    </span>
                  )}
                </>
              )}
              <span className="review-source">
                {document?.file_name ?? 'Source document'}
                {fact.page_number ? ` · Page ${fact.page_number}` : ''}
              </span>
              {viewError && <span className="notice notice-error" role="alert">{viewError}</span>}
              {document && (
                <button
                  className="text-link review-source-action"
                  type="button"
                  onClick={() => void handleViewDocument(document.id)}
                >
                  <Eye size={15} /> View original
                </button>
              )}
              {fact.source_excerpt && (
                <blockquote className="review-evidence">
                  “{evidenceText}”
                </blockquote>
              )}
            </div>
            <div className="review-actions">
              {isEditing ? (
                <button
                  className="review-reject"
                  type="button"
                  disabled={busyFact === fact.id}
                  onClick={() => setEditingFact(null)}
                >
                  Cancel
                </button>
              ) : (
                <button
                  className="review-reject"
                  type="button"
                  disabled={busyFact === fact.id}
                  onClick={() => {
                    setDraft({
                      factType: fact.fact_type,
                      value: fact.value,
                      eventDate: fact.event_date ?? '',
                    })
                    setEditingFact(fact.id)
                    setError('')
                  }}
                  aria-label={`Edit ${fact.fact_type}`}
                >
                  <Pencil size={16} /><span>Edit</span>
                </button>
              )}
              <button
                className="review-reject"
                type="button"
                disabled={busyFact === fact.id}
                onClick={() => void handleReview(fact, 'rejected')}
                aria-label={`Reject ${fact.fact_type}`}
              >
                <X size={16} /><span>Dismiss</span>
              </button>
              <button
                className="review-accept"
                type="button"
                disabled={busyFact === fact.id}
                onClick={() => void handleReview(fact, 'accepted')}
              >
                <Check size={16} /><span>{busyFact === fact.id ? 'Saving…' : isEditing ? 'Save & confirm' : 'Confirm detail'}</span>
              </button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
