import { QueryClient, QueryClientProvider, useQueries, useQuery } from '@tanstack/react-query'
import {
  Activity,
  ArrowDownToLine,
  ArrowUpRight,
  BookOpenText,
  FileClock,
  FileText,
  HeartPulse,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  ShieldCheck,
  SlidersHorizontal,
  Stethoscope,
  X,
} from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useOutletContext,
} from 'react-router-dom'

import { AccountActions } from './components/AccountActions'
import { AuthCard } from './components/AuthCard'
import { DocumentUpload } from './components/DocumentUpload'
import { HealthTimeline } from './components/HealthTimeline'
import { LifestylePage } from './components/LifestylePage'
import { ReviewQueue } from './components/ReviewQueue'
import { RecordsQuestions } from './components/RecordsQuestions'
import { HealthKnowledgePage } from './components/HealthKnowledgePage'
import {
  getCurrentUser,
  getDocumentFacts,
  getDocuments,
  getTimeline,
  downloadDocument,
  extractDocumentFacts,
  logoutUser,
} from './lib/api'
import type { DocumentRecord, MedicalFact, User } from './types'

const queryClient = new QueryClient()

const navigation = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/records', label: 'Health records', icon: FileText, end: false },
  { to: '/timeline', label: 'Health timeline', icon: Activity, end: false },
  { to: '/questions', label: 'Ask your records', icon: MessageSquareText, end: false },
  { to: '/health-info', label: 'Health information', icon: BookOpenText, end: false },
  { to: '/lifestyle', label: 'Lifestyle', icon: HeartPulse, end: false },
  { to: '/settings', label: 'Account settings', icon: SlidersHorizontal, end: false },
]

type AppPageContext = {
  user: User
  documents: DocumentRecord[]
  facts: MedicalFact[]
  timelineFacts: MedicalFact[]
  acceptedFacts: MedicalFact[]
  isLoading: boolean
  loadError: string
  refreshRecords: () => void
  onAccountDeleted: () => void
}

function useAppPage() {
  return useOutletContext<AppPageContext>()
}

function AppLayout() {
  const [loggedOut, setLoggedOut] = useState(false)
  const [authVersion, setAuthVersion] = useState(0)
  const [logoutError, setLogoutError] = useState('')
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false)
  const location = useLocation()

  const userQuery = useQuery({
    queryKey: ['me', authVersion],
    queryFn: getCurrentUser,
    retry: false,
  })
  const documentsQuery = useQuery({
    queryKey: ['documents', authVersion],
    enabled: Boolean(userQuery.data) && !loggedOut,
    queryFn: getDocuments,
  })
  const timelineQuery = useQuery({
    queryKey: ['timeline', authVersion],
    enabled: Boolean(userQuery.data) && !loggedOut,
    queryFn: getTimeline,
  })
  const factsQueries = useQueries({
    queries: (documentsQuery.data ?? []).map((document) => ({
      queryKey: ['document-facts', authVersion, document.id],
      queryFn: () => getDocumentFacts(document.id),
      enabled: Boolean(userQuery.data) && !loggedOut,
    })),
  })

  const documents = documentsQuery.data ?? []
  const facts = useMemo(
    () => factsQueries.flatMap((query) => query.data ?? []),
    [factsQueries],
  )
  const timelineFacts = timelineQuery.data ?? []
  const acceptedFacts = timelineFacts.filter((fact) => fact.status === 'accepted')
  const factsError = factsQueries.find((query) => query.error)?.error
  const loadError = [documentsQuery.error, timelineQuery.error, factsError]
    .find((error): error is Error => error instanceof Error)?.message ?? ''
  const isLoading = documentsQuery.isLoading || timelineQuery.isLoading || factsQueries.some((query) => query.isLoading)

  const refreshRecords = () => {
    void queryClient.invalidateQueries({ queryKey: ['documents'] })
    void queryClient.invalidateQueries({ queryKey: ['timeline'] })
    void queryClient.invalidateQueries({ queryKey: ['document-facts'] })
  }
  const handleAccountDeleted = () => {
    queryClient.clear()
    setLoggedOut(true)
  }

  const handleLogout = async () => {
    setLogoutError('')
    try {
      await logoutUser()
      queryClient.clear()
      setLoggedOut(true)
      setMobileNavigationOpen(false)
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : 'Could not log out')
    }
  }

  const handleLoggedIn = () => {
    setLoggedOut(false)
    setAuthVersion((version) => version + 1)
  }

  if (userQuery.isPending && !loggedOut) {
    return (
      <main className="session-screen" role="status">
        <div className="session-spinner" />
        <p>Opening your private health space…</p>
      </main>
    )
  }

  if (loggedOut || userQuery.isError || !userQuery.data) {
    return (
      <main className="auth-layout">
        <section className="auth-story">
          <div className="brand-lockup">
            <span className="brand-mark"><HeartPulse size={22} strokeWidth={2.4} /></span>
            <span>MediCare<span className="brand-period">.</span></span>
          </div>
          <div className="auth-story-copy">
            <span className="eyebrow">Your health, in one place</span>
            <h1>A clearer picture of your health journey.</h1>
            <p>Keep your records organized, review what matters, and build a timeline you can understand.</p>
          </div>
          <div className="auth-trust-note">
            <ShieldCheck size={18} />
            <span>Your records are private to your account.</span>
          </div>
        </section>
        <section className="auth-form-area">
          <AuthCard onLoggedIn={handleLoggedIn} />
        </section>
      </main>
    )
  }

  const context: AppPageContext = {
    user: userQuery.data,
    documents,
    facts,
    timelineFacts,
    acceptedFacts,
    isLoading,
    loadError,
    refreshRecords,
    onAccountDeleted: handleAccountDeleted,
  }
  const displayName = userQuery.data.full_name || 'there'
  const currentPage = navigation.find((item) => (
    item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)
  ))
  const initials = displayName.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()

  return (
    <div className="app-frame">
      {mobileNavigationOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileNavigationOpen(false)}
        />
      )}
      <aside className={`sidebar${mobileNavigationOpen ? ' sidebar-open' : ''}`}>
        <Link className="brand-lockup sidebar-brand" to="/" onClick={() => setMobileNavigationOpen(false)}>
          <span className="brand-mark"><HeartPulse size={21} strokeWidth={2.4} /></span>
          <span>MediCare<span className="brand-period">.</span></span>
        </Link>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `sidebar-link${isActive ? ' sidebar-link-active' : ''}`}
              onClick={() => setMobileNavigationOpen(false)}
            >
              <Icon size={18} strokeWidth={1.9} />
              <span>{label}</span>
              {label === 'Health records' && documents.length > 0 && (
                <span className="sidebar-count">{documents.length}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-spacer" />
        <div className="sidebar-privacy">
          <div className="privacy-icon"><ShieldCheck size={17} /></div>
          <div>
            <strong>Your space is private</strong>
            <span>Only you can access your records.</span>
          </div>
        </div>
        <div className="sidebar-user">
          <span className="avatar">{initials || 'M'}</span>
          <span className="sidebar-user-copy">
            <strong>{displayName}</strong>
            <span>Personal account</span>
          </span>
          <button className="icon-button sidebar-logout" onClick={() => void handleLogout()} aria-label="Log out" title="Log out">
            <LogOut size={17} />
          </button>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <button
            className="icon-button mobile-menu-button"
            aria-label={mobileNavigationOpen ? 'Close navigation' : 'Open navigation'}
            onClick={() => setMobileNavigationOpen((open) => !open)}
          >
            {mobileNavigationOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="topbar-breadcrumb">
            <span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{currentPage?.label ?? 'Overview'}</strong>
          </div>
          <div className="topbar-right">
            <span className="topbar-secure"><ShieldCheck size={15} /> Private & secure</span>
            <Link className="topbar-avatar" to="/settings" aria-label="Open account settings">{initials || 'M'}</Link>
          </div>
        </header>

        {logoutError && <div className="global-error" role="alert">{logoutError}</div>}
        <main className="page-content">
          <Outlet context={context} />
        </main>
        <footer className="app-footer">
          <span>MediCare is an organization tool, not a medical service.</span>
          <span><ShieldCheck size={14} /> Your records stay yours</span>
        </footer>
      </div>
    </div>
  )
}

function PageHeading({ eyebrow, title, description, action }: {
  eyebrow: string
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {action}
    </div>
  )
}

function QueryState({ loading, error }: { loading: boolean; error: string }) {
  if (loading) return <div className="inline-state"><span className="session-spinner" /> Loading your records…</div>
  if (error) return <div className="notice notice-error" role="alert">{error}</div>
  return null
}

function OverviewPage() {
  const { user, documents, facts, acceptedFacts, isLoading, loadError } = useAppPage()
  const needsReview = facts.filter((fact) => fact.status === 'unreviewed').length
  const greeting = user.full_name?.trim().split(/\s+/)[0] || 'there'
  const recentDocuments = [...documents].sort(
    (a, b) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime(),
  ).slice(0, 4)

  return (
    <>
      <section className="welcome-banner">
        <div className="welcome-orbit welcome-orbit-one" />
        <div className="welcome-orbit welcome-orbit-two" />
        <div className="welcome-content">
          <span className="welcome-kicker"><span className="welcome-pulse" /> YOUR PERSONAL HEALTH SPACE</span>
          <h1>Good to see you, {greeting}.</h1>
          <p>Your health information, organized around you. One step at a time.</p>
          <div className="welcome-actions">
            <Link to="/records" className="welcome-button">Explore your records <ArrowUpRight size={17} /></Link>
            <Link to="/timeline" className="welcome-button">Open health timeline <Activity size={17} /></Link>
          </div>
        </div>
        <div className="welcome-illustration" aria-hidden="true">
          <div className="illustration-ring ring-back" />
          <div className="illustration-ring ring-front" />
          <div className="illustration-card">
            <span className="illustration-card-icon"><HeartPulse size={23} /></span>
            <span className="illustration-line line-long" />
            <span className="illustration-line line-short" />
            <span className="illustration-check"><ShieldCheck size={19} /></span>
          </div>
          <span className="illustration-dot dot-one" />
          <span className="illustration-dot dot-two" />
        </div>
      </section>

      <div className="section-heading overview-section-heading">
        <div>
          <h2>Your health at a glance</h2>
          <p>A simple snapshot of what you have in your space.</p>
        </div>
        <span className="updated-label"><span className="live-dot" /> Your personal overview</span>
      </div>
      <QueryState loading={isLoading} error={loadError} />

      <section className="stat-grid" aria-label="Health record summary">
        <article className="stat-card">
          <div className="stat-icon stat-blue"><FileText size={19} /></div>
          <span className="stat-label">Health records</span>
          <strong className="stat-value">{documents.length}</strong>
          <span className="stat-footnote">Documents in your space</span>
        </article>
        <article className="stat-card">
          <div className="stat-icon stat-green"><Activity size={19} /></div>
          <span className="stat-label">Reviewed facts</span>
          <strong className="stat-value">{acceptedFacts.length}</strong>
          <span className="stat-footnote">Confirmed by you</span>
        </article>
        <article className={`stat-card${needsReview ? ' stat-card-highlight' : ''}`}>
          <div className="stat-icon stat-amber"><FileClock size={19} /></div>
          <span className="stat-label">To review</span>
          <strong className="stat-value">{needsReview}</strong>
          <span className="stat-footnote">Items need your attention</span>
        </article>
      </section>

      <section className="overview-lower-grid">
        <div className="panel recent-panel">
          <div className="panel-heading">
            <div><h2>Recently added</h2><p>Your latest health documents</p></div>
            <Link className="text-link" to="/records">View all <ArrowUpRight size={15} /></Link>
          </div>
          {recentDocuments.length === 0 ? (
            <div className="empty-state compact-empty">
              <span className="empty-icon"><FileText size={21} /></span>
              <strong>Your records will appear here</strong>
              <span>Add a document to start building your personal health history.</span>
              <Link to="/records" className="text-link">Add your first record <ArrowUpRight size={15} /></Link>
            </div>
          ) : (
            <ul className="recent-list">
              {recentDocuments.map((document) => (
                <li key={document.id} className="recent-item">
                  <span className="document-icon"><FileText size={18} /></span>
                  <span className="recent-item-copy">
                    <strong>{document.file_name}</strong>
                    <span>{new Date(document.uploaded_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                  </span>
                  <span className={`status-pill status-${document.status}`}>{document.status.replace('_', ' ')}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <aside className="panel next-step-panel">
          <div className="next-step-icon"><Stethoscope size={21} /></div>
          <span className="next-step-label">A helpful next step</span>
          <h2>Keep your history up to date</h2>
          <p>Add a visit summary, test result, or medication list. Extracted details appear on your timeline right away, ready for you to edit.</p>
          <Link to="/records" className="text-link">Go to health records <ArrowUpRight size={15} /></Link>
          <div className="next-step-decoration" aria-hidden="true"><Activity size={72} /></div>
        </aside>
      </section>
    </>
  )
}

function RecordsPage() {
  const { documents, facts, isLoading, loadError, refreshRecords } = useAppPage()
  const reviewFacts = facts.filter((fact) => fact.status === 'unreviewed')
  const [downloadError, setDownloadError] = useState('')
  const [extractingDocumentId, setExtractingDocumentId] = useState<number | null>(null)
  const [extractError, setExtractError] = useState('')
  const [extractMessage, setExtractMessage] = useState('')
  const records = documents

  return (
    <>
      <PageHeading
        eyebrow="YOUR LIBRARY"
        title="Health records"
        description="A private home for the documents that help tell your health story."
        action={<span className="heading-count"><FileText size={16} /> {records.length} {records.length === 1 ? 'record' : 'records'}</span>}
      />
      <section className="records-upload-panel">
        <div className="records-upload-copy">
          <span className="upload-panel-icon"><ArrowDownToLine size={20} /></span>
          <div>
            <h2>Add a health document</h2>
            <p>Upload a visit summary, test result, prescription, or other record.</p>
          </div>
        </div>
        <DocumentUpload onUploaded={refreshRecords} />
      </section>

      <QueryState loading={isLoading} error={loadError} />
      {extractError && <div className="notice notice-error" role="alert">{extractError}</div>}
      {extractMessage && <div className="notice notice-success" role="status">{extractMessage}</div>}
      <section className="panel review-panel">
        <div className="panel-heading">
          <div>
            <h2>Extracted details</h2>
            <p>These appear on your timeline as soon as they’re extracted. Edit or dismiss anything that needs correcting.</p>
          </div>
          {reviewFacts.length > 0 && <span className="review-count">{reviewFacts.length} extracted</span>}
        </div>
        <ReviewQueue
          facts={reviewFacts}
          documents={records}
          noFactsDetected={!isLoading && !loadError && records.length > 0 && facts.length === 0}
          onReviewed={refreshRecords}
        />
      </section>

      <section className="panel records-panel">
        <div className="panel-heading">
          <div><h2>All documents</h2><p>Your originals stay available to you.</p></div>
        </div>
        {downloadError && <div className="notice notice-error" role="alert">{downloadError}</div>}
        {records.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon"><FileText size={24} /></span>
            <strong>No records yet</strong>
            <span>Upload your first document above. Supported files include PDF, PNG, JPEG, TXT, and MD.</span>
          </div>
        ) : (
          <ul className="document-list">
            {records.map((document) => {
              const documentFacts = facts.filter((fact) => fact.document_id === document.id && fact.status !== 'rejected')
              return (
                <li className="document-list-item" key={document.id}>
                <span className="document-icon document-icon-large"><FileText size={19} /></span>
                <div className="document-list-copy">
                  <strong>{document.file_name}</strong>
                  <span>
                    {document.document_type ?? 'Health document'}
                    {document.document_date ? ` · ${document.document_date}` : ''}
                    {' · Added '}
                    {new Date(document.uploaded_at).toLocaleDateString()}
                  </span>
                  {document.status === 'manual_review' && <small>No readable text was found. Review the original manually.</small>}
                  {document.status === 'ocr_review' && <small>OCR was used. Check extracted details against the original before accepting.</small>}
                </div>
                <span className={`status-pill status-${document.status}`}>{document.status.replace('_', ' ')}</span>
                <button
                  className="secondary-btn download-button"
                  type="button"
                  onClick={async () => {
                    setDownloadError('')
                    try {
                      await downloadDocument(document.id, document.file_name)
                    } catch (error) {
                      setDownloadError(error instanceof Error ? error.message : 'Unable to download this document')
                    }
                  }}
                >
                  Download original
                </button>
                <button
                  className="secondary-btn download-button"
                  type="button"
                  disabled={extractingDocumentId === document.id}
                  onClick={async () => {
                    setExtractError('')
                    setExtractMessage('')
                    setExtractingDocumentId(document.id)
                    try {
                      const result = await extractDocumentFacts(document.id)
                      const changes = result.extracted_fact_count + result.updated_fact_count
                      setExtractMessage(changes
                        ? `Updated ${changes} extracted detail${changes === 1 ? '' : 's'} from this record. Check your timeline.`
                        : 'No new details or dates were found. You can open the original and edit a timeline detail manually.')
                      refreshRecords()
                    } catch (error) {
                      setExtractError(error instanceof Error ? error.message : 'Could not extract this document')
                    } finally {
                      setExtractingDocumentId(null)
                    }
                  }}
                >
                  {extractingDocumentId === document.id ? 'Extracting…' : documentFacts.length ? 'Refresh extracted details' : 'Extract details now'}
                </button>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </>
  )
}

function TimelinePage() {
  const { documents, timelineFacts, isLoading, loadError, refreshRecords } = useAppPage()
  const eventDates = timelineFacts
    .map((fact) => fact.event_date)
    .filter((eventDate): eventDate is string => Boolean(eventDate))
    .sort()
  const dateRange = eventDates.length
    ? `${new Date(`${eventDates[0]}T12:00:00`).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })} – ${new Date(`${eventDates[eventDates.length - 1]}T12:00:00`).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}`
    : null
  return (
    <>
      <PageHeading
        eyebrow="YOUR HEALTH HISTORY"
        title="Health timeline"
        description="Your health history, organized chronologically from the medical details you review."
        action={(
          <div className="timeline-header-actions">
            <span className="heading-count">
              <Activity size={16} /> {timelineFacts.length} {timelineFacts.length === 1 ? 'timeline detail' : 'timeline details'}
            </span>
            {dateRange && <span className="timeline-date-range">{dateRange}</span>}
            <Link className="secondary-btn" to="/records">Add medical records</Link>
          </div>
        )}
      />
      <QueryState loading={isLoading} error={loadError} />
      <div className="timeline-disclaimer">
        <ShieldCheck size={18} />
        <p>Extracted details appear here immediately and can be edited at any time. Items marked “Extracted” have not been checked by you; dates are shown only when recorded in the source. This is your personal record—not a clinical assessment.</p>
      </div>
      <HealthTimeline
        documents={documents}
        timeline={timelineFacts}
        onFactUpdated={refreshRecords}
      />
    </>
  )
}

function LifestyleRecordsPage() {
  const { facts, documents, refreshRecords } = useAppPage()
  return <LifestylePage facts={facts} documents={documents} onFactsReviewed={refreshRecords} />
}

function SettingsPage() {
  const { user, documents, acceptedFacts, onAccountDeleted } = useAppPage()
  const initials = user.full_name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
  return (
    <>
      <PageHeading
        eyebrow="PREFERENCES & PRIVACY"
        title="Account settings"
        description="Review your account details and manage your personal data."
      />
      <section className="settings-profile-card">
        <span className="settings-avatar">{initials || 'M'}</span>
        <div className="settings-profile-copy">
          <span className="profile-overline">PERSONAL ACCOUNT</span>
          <h2>{user.full_name}</h2>
          <p>{user.email}</p>
        </div>
        <span className="verified-label"><ShieldCheck size={15} /> Private account</span>
      </section>

      <div className="settings-grid">
        <div className="settings-main-column">
          <section className="panel settings-panel">
            <div className="panel-heading">
              <div><h2>Profile details</h2><p>Your account information</p></div>
            </div>
            <div className="settings-fields">
              <div className="settings-field">
                <span>Full name</span><strong>{user.full_name}</strong>
              </div>
              <div className="settings-field">
                <span>Email address</span><strong>{user.email}</strong>
              </div>
              <div className="settings-field">
                <span>Account ID</span><strong className="monospace-value">MC-{String(user.id).padStart(6, '0')}</strong>
              </div>
            </div>
            <p className="settings-footnote">Profile editing isn’t available yet. Your account details are shown as currently registered.</p>
          </section>
          <section className="panel settings-panel">
            <div className="panel-heading">
              <div><h2>Privacy & security</h2><p>How MediCare protects your account</p></div>
            </div>
            <ul className="security-list">
              <li><span className="security-list-icon"><ShieldCheck size={17} /></span><span><strong>Private by account</strong><small>Your records are scoped to your account.</small></span><span className="security-status">On</span></li>
              <li><span className="security-list-icon"><HeartPulse size={17} /></span><span><strong>Reviewable timeline details</strong><small>Extracted details appear immediately and stay marked unconfirmed until you confirm them.</small></span><span className="security-status">On</span></li>
            </ul>
          </section>
        </div>
        <aside className="settings-side-column">
          <section className="panel data-summary-panel">
            <div className="panel-heading"><div><h2>Your data</h2><p>Stored in your account</p></div></div>
            <div className="data-summary-row"><span>Documents</span><strong>{documents.length}</strong></div>
            <div className="data-summary-row"><span>Reviewed facts</span><strong>{acceptedFacts.length}</strong></div>
            <div className="data-summary-note"><ShieldCheck size={15} /> You can export a copy at any time.</div>
          </section>
          <AccountActions onDeleted={onAccountDeleted} />
        </aside>
      </div>
    </>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<OverviewPage />} />
            <Route path="records" element={<RecordsPage />} />
            <Route path="timeline" element={<TimelinePage />} />
            <Route path="questions" element={<RecordsQuestions />} />
            <Route path="health-info" element={<HealthKnowledgePage />} />
            <Route path="lifestyle" element={<LifestyleRecordsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
