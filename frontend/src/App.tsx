import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom'

import { AuthCard } from './components/AuthCard'
import { AccountActions } from './components/AccountActions'
import { DocumentUpload } from './components/DocumentUpload'
import { HealthTimeline } from './components/HealthTimeline'
import { getCurrentUser, getDocuments, getTimeline, logoutUser } from './lib/api'

const queryClient = new QueryClient()

function AppLayout() {
  const [loggedOut, setLoggedOut] = useState(false)
  const [authVersion, setAuthVersion] = useState(0)
  const [logoutError, setLogoutError] = useState('')

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

  const handleLogout = async () => {
    setLogoutError('')
    try {
      await logoutUser()
      queryClient.clear()
      setLoggedOut(true)
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : 'Could not log out')
    }
  }

  const handleLoggedIn = () => {
    setLoggedOut(false)
    setAuthVersion((version) => version + 1)
  }

  if (userQuery.isPending && !loggedOut) {
    return <main className="page-shell" role="status">Checking your secure session...</main>
  }

  if (loggedOut || userQuery.isError || !userQuery.data) {
    return (
      <div className="page-shell">
        <header className="topbar">
          <div>
            <p className="eyebrow">MediCare</p>
            <h1 className="text-3xl font-bold">Personal health intelligence</h1>
          </div>
        </header>

        <main className="main-panel">
          <AuthCard onLoggedIn={handleLoggedIn} />
        </main>
      </div>
    )
  }

  return (
    <div className="page-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">MediCare</p>
          <h1 className="text-3xl font-bold">Welcome, {userQuery.data.full_name || 'patient'}</h1>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/" className="nav-link">Dashboard</Link>
          <button className="secondary-btn" onClick={() => void handleLogout()}>
            Log out
          </button>
        </div>
      </header>

      {logoutError && <p className="text-sm text-red-600 mb-4" role="alert">{logoutError}</p>}

      <main className="space-y-6">
        <AccountActions onDeleted={() => {
          queryClient.clear()
          setLoggedOut(true)
        }} />

        <DocumentUpload onUploaded={() => {
          void documentsQuery.refetch()
          void timelineQuery.refetch()
        }} />

        <HealthTimeline
          documents={documentsQuery.data ?? []}
          timeline={timelineQuery.data ?? []}
          onReviewed={() => {
            void documentsQuery.refetch()
            void timelineQuery.refetch()
          }}
        />
      </main>
    </div>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
