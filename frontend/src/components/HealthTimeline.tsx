import { useMemo, useState } from 'react'
import { Activity, ArrowRight, Eye, FileText, Pencil, X } from 'lucide-react'
import { Link } from 'react-router-dom'

import { reviewFact, viewDocument } from '../lib/api'
import type { DocumentRecord, MedicalFact } from '../types'

type Props = {
  documents: DocumentRecord[]
  timeline: MedicalFact[]
  onFactUpdated: () => void
}

export function HealthTimeline({ documents, timeline, onFactUpdated }: Props) {
  const [category, setCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [sourceError, setSourceError] = useState('')
  const [editingFact, setEditingFact] = useState<number | null>(null)
  const [draft, setDraft] = useState({ factType: '', value: '', eventDate: '' })
  const [savingFact, setSavingFact] = useState<number | null>(null)
  const [editError, setEditError] = useState('')
  const chronologicalFacts = [...timeline].sort(
    (a, b) => {
      const dateA = a.event_date ? new Date(`${a.event_date}T00:00:00`).getTime() : 0
      const dateB = b.event_date ? new Date(`${b.event_date}T00:00:00`).getTime() : 0
      return dateB - dateA || new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    },
  )
  const filteredFacts = useMemo(
    () => chronologicalFacts.filter((fact) => {
      const isLifestyle = fact.fact_type.startsWith('lifestyle_')
      const factCategory = isLifestyle
        ? 'lifestyle'
        : ['lab', 'measurement', 'vital'].includes(fact.fact_type)
          ? 'tests'
          : ['procedure', 'provider', 'visit'].includes(fact.fact_type)
            ? 'care'
            : fact.fact_type
      const matchesCategory = category === 'all' || category === factCategory
      const source = documents.find((document) => document.id === fact.document_id)
      const haystack = `${fact.fact_type} ${fact.value} ${source?.file_name ?? ''}`.toLocaleLowerCase()
      return matchesCategory && haystack.includes(search.trim().toLocaleLowerCase())
    }),
    [category, chronologicalFacts, documents, search],
  )

  const saveFact = async (fact: MedicalFact) => {
    if (!draft.factType.trim() || !draft.value.trim()) {
      setEditError('Enter both a detail type and value.')
      return
    }
    setSavingFact(fact.id)
    setEditError('')
    try {
      await reviewFact(fact.id, {
        status: fact.status === 'accepted' ? 'accepted' : 'unreviewed',
        fact_type: draft.factType.trim(),
        value: draft.value.trim(),
        event_date: draft.eventDate || null,
        clear_event_date: !draft.eventDate,
      })
      setEditingFact(null)
      onFactUpdated()
    } catch (error) {
      setEditError(error instanceof Error ? error.message : 'Could not save this timeline detail')
    } finally {
      setSavingFact(null)
    }
  }

  if (!chronologicalFacts.length) {
    return (
      <div className="panel empty-state timeline-empty">
        <span className="empty-icon"><Activity size={23} /></span>
        <strong>No health details to show yet</strong>
        {documents.length > 0 ? (
          <>
            <span>You have {documents.length} uploaded {documents.length === 1 ? 'record' : 'records'}, but none has an extractable detail yet. Open your records to view the originals or add a detail manually.</span>
            <Link className="primary-btn timeline-empty-action" to="/records">
              Open health records <ArrowRight size={16} />
            </Link>
          </>
        ) : (
          <>
            <span>Upload a health record and extracted details will appear here automatically. You can edit them at any time.</span>
            <Link className="primary-btn timeline-empty-action" to="/records">
              Add medical records <ArrowRight size={16} />
            </Link>
          </>
        )}
      </div>
    )
  }

  return (
    <>
      <div className="timeline-filters" role="search">
        <label>
          <span>Filter by category</span>
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="all">All health details</option>
            <option value="diagnosis">Diagnoses</option>
            <option value="symptom">Symptoms</option>
            <option value="medication">Medications</option>
            <option value="allergy">Allergies</option>
            <option value="tests">Tests & measurements</option>
            <option value="care">Procedures & care</option>
            <option value="lifestyle">Lifestyle details</option>
          </select>
        </label>
        <label>
          <span>Search timeline</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search details or source file"
          />
        </label>
        <span className="timeline-filter-count">{filteredFacts.length} of {chronologicalFacts.length} details</span>
      </div>
      {filteredFacts.length ? (
        <ol className="timeline-list">
          {filteredFacts.map((fact, index) => {
            const source = documents.find((document) => document.id === fact.document_id)
            const eventDate = fact.event_date ? new Date(`${fact.event_date}T12:00:00`) : null
            const isAi = fact.source_excerpt?.includes('AI suggestion:') ?? false
            const isUserEntered = fact.source_excerpt?.startsWith('User-entered from') ?? false
            const evidenceText = fact.source_excerpt?.replace(/^(?:OCR text|OCR \+ AI suggestion|AI suggestion):\s*/, '')
            const isEditing = editingFact === fact.id
            return (
              <li className="timeline-entry" key={fact.id}>
                <span className={`timeline-marker${index === 0 ? ' timeline-marker-current' : ''}`}>
                  <span />
                </span>
                <article className="panel timeline-card">
                  <div className="timeline-card-heading">
                    <div>
                      <span className="timeline-date">
                        {eventDate
                          ? `EVENT DATE · ${eventDate.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}`
                          : 'DATE NOT RECORDED'}
                      </span>
                      <h2>
                        {fact.fact_type.replace(/^lifestyle_/, '').replace(/_/g, ' ').replace(/^\w/, (letter) => letter.toUpperCase())}
                      </h2>
                    </div>
                    <span className={fact.status === 'accepted' ? 'accepted-label' : 'timeline-extracted-label'}>
                      {fact.status === 'accepted'
                        ? 'Confirmed by you'
                        : isUserEntered
                          ? 'Added by you · unconfirmed'
                          : 'Extracted · editable'}
                    </span>
                  </div>
                  {isEditing ? (
                    <div className="timeline-edit-fields">
                      <label>
                        <span>Detail type</span>
                        <input
                          value={draft.factType}
                          maxLength={64}
                          onChange={(event) => setDraft((current) => ({ ...current, factType: event.target.value }))}
                        />
                      </label>
                      <label>
                        <span>Detail</span>
                        <textarea
                          value={draft.value}
                          maxLength={2000}
                          rows={3}
                          onChange={(event) => setDraft((current) => ({ ...current, value: event.target.value }))}
                        />
                      </label>
                      <label>
                        <span>Event date (only if stated in the source)</span>
                        <input
                          type="date"
                          value={draft.eventDate}
                          onChange={(event) => setDraft((current) => ({ ...current, eventDate: event.target.value }))}
                        />
                      </label>
                      {editError && <span className="notice notice-error" role="alert">{editError}</span>}
                      <div className="timeline-edit-actions">
                        <button
                          className="secondary-btn"
                          type="button"
                          onClick={() => {
                            setEditingFact(null)
                            setEditError('')
                          }}
                          disabled={savingFact === fact.id}
                        >
                          <X size={15} /> Cancel
                        </button>
                        <button
                          className="primary-btn"
                          type="button"
                          onClick={() => void saveFact(fact)}
                          disabled={savingFact === fact.id}
                        >
                          {savingFact === fact.id ? 'Saving…' : 'Save changes'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="timeline-value">{fact.value}</p>
                  )}
                  {!isEditing && fact.numeric_value !== null && fact.numeric_value !== undefined && (
                    <p className="timeline-measurement">
                      Parsed measurement: {fact.numeric_value}{fact.unit ? ` ${fact.unit}` : ''}
                      {' · Verify the original document before relying on this value.'}
                    </p>
                  )}
                  {!isEditing && fact.source_excerpt && (
                    <blockquote className="timeline-evidence">
                      <span>FROM YOUR RECORD</span>
                      <p>“{evidenceText}”</p>
                    </blockquote>
                  )}
                  <div className="timeline-source">
                    <FileText size={15} />
                    <span>{source?.file_name ?? 'Original source document'}</span>
                    {fact.page_number && <span>· Page {fact.page_number}</span>}
                    {(fact.source_excerpt?.startsWith('OCR text:') || fact.source_excerpt?.startsWith('OCR + AI suggestion:')) && (
                      <span className="ocr-label">OCR assisted</span>
                    )}
                    {isAi && <span className="ai-label">AI suggestion</span>}
                  </div>
                  {source && (
                    <button
                      className="text-link timeline-source-action"
                      type="button"
                      onClick={() => {
                        setSourceError('')
                        void viewDocument(source.id).catch((error: unknown) => {
                          setSourceError(error instanceof Error ? error.message : 'Unable to open this source document')
                        })
                      }}
                    >
                      <Eye size={15} /> View source document
                    </button>
                  )}
                  {!isEditing && (
                    <button
                      className="text-link timeline-source-action"
                      type="button"
                      onClick={() => {
                        setDraft({
                          factType: fact.fact_type,
                          value: fact.value,
                          eventDate: fact.event_date ?? '',
                        })
                        setEditingFact(fact.id)
                        setEditError('')
                      }}
                    >
                      <Pencil size={15} /> Edit detail
                    </button>
                  )}
                </article>
              </li>
            )
          })}
        </ol>
      ) : (
        <div className="panel timeline-filter-empty" role="status">
          No health details match these filters. Try another category or search term.
        </div>
      )}
      {sourceError && <div className="notice notice-error" role="alert">{sourceError}</div>}
    </>
  )
}
