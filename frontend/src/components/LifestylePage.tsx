import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, HeartPulse, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

import { getLifestyleProfile, saveLifestyleProfile } from '../lib/api'
import type {
  ActivityFrequency,
  AlcoholFrequency,
  DocumentRecord,
  LifestyleProfile,
  LifestyleProfileInput,
  MedicalFact,
  TobaccoUse,
} from '../types'
import { ReviewQueue } from './ReviewQueue'

type Props = {
  facts: MedicalFact[]
  documents: DocumentRecord[]
  onFactsReviewed: () => void
}

const emptyProfile: LifestyleProfileInput = {
  activity_frequency: null,
  diet_notes: null,
  sleep_hours: null,
  tobacco_use: null,
  alcohol_frequency: null,
  notes: null,
}

const activityOptions: ActivityFrequency[] = ['rarely', '1-2 days/week', '3-4 days/week', '5+ days/week']
const tobaccoOptions: TobaccoUse[] = ['never', 'former', 'current', 'prefer_not_to_say']
const alcoholOptions: AlcoholFrequency[] = ['never', 'occasionally', 'weekly', 'daily', 'prefer_not_to_say']

function nullableOption<T extends string>(value: string, options: readonly T[]): T | null {
  return options.find((option) => option === value) ?? null
}

export function LifestylePage({ facts, documents, onFactsReviewed }: Props) {
  const profileQuery = useQuery({
    queryKey: ['lifestyle'],
    queryFn: getLifestyleProfile,
    retry: false,
  })
  if (profileQuery.isPending) {
    return <div className="inline-state"><span className="session-spinner" /> Loading your lifestyle profile…</div>
  }

  if (profileQuery.isError) {
    return <div className="notice notice-error" role="alert">{profileQuery.error.message}</div>
  }

  return (
    <LifestyleQuestionnaire
      profile={profileQuery.data}
      facts={facts.filter((fact) => fact.fact_type.startsWith('lifestyle_'))}
      documents={documents}
      onFactsReviewed={onFactsReviewed}
    />
  )
}

function LifestyleQuestionnaire({
  profile,
  facts,
  documents,
  onFactsReviewed,
}: {
  profile: LifestyleProfile | null
  facts: MedicalFact[]
  documents: DocumentRecord[]
  onFactsReviewed: () => void
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<LifestyleProfileInput>(() => profile
    ? {
      activity_frequency: profile.activity_frequency,
      diet_notes: profile.diet_notes,
      sleep_hours: profile.sleep_hours,
      tobacco_use: profile.tobacco_use,
      alcohol_frequency: profile.alcohol_frequency,
      notes: profile.notes,
    }
    : emptyProfile)
  const [saved, setSaved] = useState(false)

  const saveMutation = useMutation({
    mutationFn: saveLifestyleProfile,
    onSuccess: (updatedProfile) => {
      setForm({
        activity_frequency: updatedProfile.activity_frequency,
        diet_notes: updatedProfile.diet_notes,
        sleep_hours: updatedProfile.sleep_hours,
        tobacco_use: updatedProfile.tobacco_use,
        alcohol_frequency: updatedProfile.alcohol_frequency,
        notes: updatedProfile.notes,
      })
      setSaved(true)
      queryClient.setQueryData(['lifestyle'], updatedProfile)
    },
  })

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaved(false)
    saveMutation.mutate(form)
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR SELF-REPORTED PROFILE</p>
          <h1>Lifestyle</h1>
          <p className="page-description">Add details about your routines at your own pace. Every answer is optional.</p>
        </div>
        <span className="heading-count"><Activity size={16} /> Personal profile</span>
      </div>

      <div className="lifestyle-notice">
        <ShieldCheck size={19} />
        <p>Your questionnaire is a separate, self-reported snapshot and is not added to the medical timeline. Lifestyle details extracted from records appear on the timeline immediately, linked to their source, and can be edited there at any time.</p>
      </div>

      <section className="panel lifestyle-records-panel">
        <div className="panel-heading">
          <div>
            <h2>Lifestyle details from your records</h2>
            <p>Extracted details are already on your timeline. You can optionally confirm, edit, or dismiss them here.</p>
          </div>
          <Link className="text-link" to="/timeline">View timeline</Link>
        </div>
        <ReviewQueue
          facts={facts.filter((fact) => fact.status === 'unreviewed')}
          documents={documents}
          noFactsDetected={false}
          onReviewed={onFactsReviewed}
        />
        {facts.some((fact) => fact.status === 'accepted') ? (
          <ul className="lifestyle-record-list">
            {facts.filter((fact) => fact.status === 'accepted').map((fact) => {
              const source = documents.find((document) => document.id === fact.document_id)
              return (
                <li key={fact.id}>
                  <div>
                    <span>{fact.fact_type.replace('lifestyle_', '').replace(/^\w/, (letter) => letter.toUpperCase())}</span>
                    <strong>{fact.value}</strong>
                    {fact.event_date && <small>Event date: {fact.event_date}</small>}
                    <small>{source?.file_name ?? 'Source document'}{fact.page_number ? ` · Page ${fact.page_number}` : ''}</small>
                    {fact.source_excerpt && (
                      <blockquote>
                        {fact.source_excerpt.replace(/^(?:OCR text|OCR \+ AI suggestion|AI suggestion):\s*/, '')}
                      </blockquote>
                    )}
                  </div>
                  <span className="accepted-label">Reviewed by you</span>
                </li>
              )
            })}
          </ul>
        ) : !facts.some((fact) => fact.status === 'unreviewed') ? (
          <div className="lifestyle-record-empty">
            No lifestyle details from uploaded documents yet. Upload a record with clearly stated lifestyle details to see them here.
          </div>
        ) : null}
      </section>

      <form className="panel lifestyle-form" onSubmit={handleSubmit}>
        <div className="lifestyle-form-heading">
          <span className="lifestyle-heading-icon"><HeartPulse size={20} /></span>
          <div>
            <h2>Your lifestyle details</h2>
            <p>Share only what you’re comfortable recording.</p>
            {profile?.updated_at && (
              <small>Last updated {new Date(profile.updated_at).toLocaleDateString()}</small>
            )}
          </div>
        </div>

        <div className="lifestyle-fields">
          <label className="lifestyle-field">
            <span>How often are you physically active?</span>
            <select
              value={form.activity_frequency ?? ''}
              onChange={(event) => setForm((current) => ({
                ...current,
                activity_frequency: nullableOption(event.target.value, activityOptions),
              }))}
            >
              <option value="">Choose an answer (optional)</option>
              {activityOptions.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>

          <label className="lifestyle-field">
            <span>About how many hours do you usually sleep?</span>
            <input
              type="number"
              min="0"
              max="24"
              step="0.5"
              value={form.sleep_hours ?? ''}
              onChange={(event) => setForm((current) => ({
                ...current,
                sleep_hours: event.target.value === '' ? null : Number(event.target.value),
              }))}
              placeholder="For example, 7.5"
            />
          </label>

          <label className="lifestyle-field">
            <span>Tobacco use</span>
            <select
              value={form.tobacco_use ?? ''}
              onChange={(event) => setForm((current) => ({
                ...current,
                tobacco_use: nullableOption(event.target.value, tobaccoOptions),
              }))}
            >
              <option value="">Choose an answer (optional)</option>
              <option value="never">Never</option>
              <option value="former">Former</option>
              <option value="current">Current</option>
              <option value="prefer_not_to_say">Prefer not to say</option>
            </select>
          </label>

          <label className="lifestyle-field">
            <span>Alcohol use</span>
            <select
              value={form.alcohol_frequency ?? ''}
              onChange={(event) => setForm((current) => ({
                ...current,
                alcohol_frequency: nullableOption(event.target.value, alcoholOptions),
              }))}
            >
              <option value="">Choose an answer (optional)</option>
              <option value="never">Never</option>
              <option value="occasionally">Occasionally</option>
              <option value="weekly">Weekly</option>
              <option value="daily">Daily</option>
              <option value="prefer_not_to_say">Prefer not to say</option>
            </select>
          </label>

          <label className="lifestyle-field lifestyle-field-wide">
            <span>Diet or nutrition notes</span>
            <textarea
              maxLength={1000}
              rows={3}
              value={form.diet_notes ?? ''}
              onChange={(event) => setForm((current) => ({
                ...current,
                diet_notes: event.target.value || null,
              }))}
              placeholder="Optional notes about your usual eating patterns"
            />
          </label>

          <label className="lifestyle-field lifestyle-field-wide">
            <span>Anything else you’d like to note?</span>
            <textarea
              maxLength={1000}
              rows={3}
              value={form.notes ?? ''}
              onChange={(event) => setForm((current) => ({
                ...current,
                notes: event.target.value || null,
              }))}
              placeholder="Optional context for your personal profile"
            />
          </label>
        </div>

        {saveMutation.isError && (
          <div className="notice notice-error" role="alert">{saveMutation.error.message}</div>
        )}
        {saved && <p className="lifestyle-saved" role="status">Your lifestyle profile has been saved.</p>}

        <div className="lifestyle-form-actions">
          <span>Optional answers · You can update these details at any time.</span>
          <button className="primary-btn" type="submit" disabled={saveMutation.isPending}>
            {saveMutation.isPending ? 'Saving…' : 'Save lifestyle details'}
          </button>
        </div>
      </form>
    </>
  )
}
