import { useState, type FormEvent } from 'react'
import { ExternalLink, Search } from 'lucide-react'

import { searchHealthKnowledge } from '../lib/api'
import type { HealthTopic } from '../types'

export function HealthKnowledgePage() {
  const [query, setQuery] = useState('')
  const [topics, setTopics] = useState<HealthTopic[] | null>(null)
  const [error, setError] = useState('')
  const [isSearching, setIsSearching] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setTopics(null)
    setIsSearching(true)
    try {
      setTopics(await searchHealthKnowledge(query.trim()))
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : 'Could not reach MedlinePlus.')
    } finally {
      setIsSearching(false)
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">GENERAL HEALTH EDUCATION</p>
          <h1>Trusted health information</h1>
          <p className="page-description">Explore accessible health-topic articles from the U.S. National Library of Medicine.</p>
        </div>
      </div>

      <div className="knowledge-privacy-notice">
        Your search topic is sent to MedlinePlus and cached by this app for up to 12 hours. No account details or medical-record content is included. Do not enter your name, personal identifiers, or details copied from your records. This page provides general education, not personal medical advice.
      </div>

      <form className="panel knowledge-search-form" onSubmit={(event) => void handleSubmit(event)}>
        <label htmlFor="health-topic-query">Search a health topic</label>
        <div className="knowledge-search-row">
          <input
            id="health-topic-query"
            value={query}
            minLength={2}
            maxLength={120}
            required
            onChange={(event) => setQuery(event.target.value)}
            placeholder="For example: understanding blood pressure"
          />
          <button className="primary-btn" type="submit" disabled={isSearching || query.trim().length < 2}>
            <Search size={17} />{isSearching ? 'Searching…' : 'Search'}
          </button>
        </div>
        <span>Search terms are sent to MedlinePlus to retrieve public health-topic results.</span>
      </form>

      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {topics && topics.length === 0 && (
        <div className="panel knowledge-empty" role="status">
          No matching topics were returned. Try a broader term or search MedlinePlus.gov directly.
        </div>
      )}
      {topics && topics.length > 0 && (
        <section className="knowledge-results" aria-live="polite" aria-label="MedlinePlus health topics">
          {topics.map((topic) => (
            <article className="panel knowledge-topic" key={topic.url}>
              <div className="knowledge-topic-source">{topic.source}</div>
              <h2>{topic.title}</h2>
              <p>{topic.summary}</p>
              <a href={topic.url} target="_blank" rel="noreferrer">
                Read the full article on MedlinePlus <ExternalLink size={15} />
              </a>
            </article>
          ))}
          <p className="knowledge-attribution">Health-topic search and excerpts are provided by MedlinePlus.gov, U.S. National Library of Medicine. MedlinePlus does not endorse MediCare.</p>
        </section>
      )}
    </>
  )
}
