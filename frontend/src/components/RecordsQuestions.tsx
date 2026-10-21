import { useState, type FormEvent } from 'react'
import { ArrowUpRight, BookOpenCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

import { askRecordsQuestion } from '../lib/api'
import type { RecordsAnswer } from '../types'

export function RecordsQuestions() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<RecordsAnswer | null>(null)
  const [error, setError] = useState('')
  const [isAsking, setIsAsking] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setAnswer(null)
    setIsAsking(true)
    try {
      setAnswer(await askRecordsQuestion(question.trim()))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not search your reviewed records.')
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR REVIEWED RECORDS</p>
          <h1>Ask your records</h1>
          <p className="page-description">Find details in information you have reviewed and accepted.</p>
        </div>
      </div>

      <div className="records-question-disclaimer">
        This uses a local keyword search over accepted facts, not an AI medical advisor. It only returns matching record details and their sources; it does not diagnose or recommend treatment.
      </div>

      <form className="panel records-question-form" onSubmit={(event) => void handleSubmit(event)}>
        <label htmlFor="records-question">What would you like to find in your records?</label>
        <textarea
          id="records-question"
          value={question}
          maxLength={500}
          rows={3}
          required
          minLength={3}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="For example: What medications have I reviewed?"
        />
        <button className="primary-btn" type="submit" disabled={isAsking || question.trim().length < 3}>
          {isAsking ? 'Searching reviewed facts…' : 'Search my records'}
        </button>
      </form>

      {error && <div className="notice notice-error" role="alert">{error}</div>}

      {answer && (
        <section className="panel records-answer" aria-live="polite">
          <div className="records-answer-heading">
            <span className="lifestyle-heading-icon"><BookOpenCheck size={20} /></span>
            <h2>From your reviewed records</h2>
          </div>
          <p>{answer.answer}</p>
          {answer.possible_conflict && (
            <div className="records-conflict" role="status">
              The records may conflict. This search cannot determine which entry is current.
            </div>
          )}
          {answer.insufficient_evidence && (
            <div className="records-insufficient" role="status">
              No supporting reviewed fact was found for this question. Unreviewed facts and unprocessed document text are not searched.
            </div>
          )}
          {answer.citations.length > 0 && (
            <div className="records-citations">
              <h3>Sources</h3>
              <ul>
                {answer.citations.map((citation, index) => (
                  <li key={`${citation.document_id}-${citation.page_number ?? 'page'}-${index}`}>
                    <strong>{citation.file_name}</strong>
                    <span>
                      {citation.event_date ? ` · Event date ${citation.event_date}` : ''}
                      {citation.page_number ? ` · Page ${citation.page_number}` : ''}
                    </span>
                    {citation.excerpt && (
                      <blockquote>“{citation.excerpt.replace(/^OCR text:\s*/, '')}”</blockquote>
                    )}
                    <Link to="/records">Open health records <ArrowUpRight size={14} /></Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </>
  )
}
