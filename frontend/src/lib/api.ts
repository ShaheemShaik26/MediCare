import type {
  DocumentRecord,
  HealthTopic,
  LifestyleProfile,
  LifestyleProfileInput,
  ManualFactType,
  MedicalFact,
  RecordsAnswer,
  User,
} from '../types'

const API_BASE = '/api'

async function responseError(response: Response): Promise<Error> {
  const body = await response.text()
  try {
    const parsed = JSON.parse(body) as { detail?: unknown }
    if (typeof parsed.detail === 'string') {
      return new Error(parsed.detail)
    }
  } catch {
    return new Error(body || 'Request failed')
  }
  return new Error(body || 'Request failed')
}

function readCsrfToken(): string | undefined {
  const value = document.cookie
    .split('; ')
    .find((cookie) => cookie.startsWith('medicare_csrf='))
    ?.split('=')
    .slice(1)
    .join('=')
  return value ? decodeURIComponent(value) : undefined
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {})
  if (init.method && !['GET', 'HEAD', 'OPTIONS'].includes(init.method.toUpperCase())) {
    const csrfToken = readCsrfToken()
    if (csrfToken) {
      headers.set('X-CSRF-Token', csrfToken)
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
  })

  if (!response.ok) {
    throw await responseError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export async function registerUser(payload: { email: string; password: string; full_name: string }): Promise<User> {
  return apiFetch<User>('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function loginUser(payload: { email: string; password: string }): Promise<User> {
  return apiFetch<User>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function logoutUser(): Promise<void> {
  await apiFetch<void>('/auth/logout', { method: 'POST' })
}

export async function deleteAccount(password: string): Promise<void> {
  await apiFetch<void>('/account', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
}

export async function downloadAccountExport(): Promise<void> {
  const response = await fetch(`${API_BASE}/account/export`, { credentials: 'same-origin' })
  if (!response.ok) {
    throw await responseError(response)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'medicare-export.zip'
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function getCurrentUser(): Promise<User> {
  return apiFetch<User>('/auth/me')
}

export async function getDocuments(): Promise<DocumentRecord[]> {
  return apiFetch<DocumentRecord[]>('/documents')
}

export async function downloadDocument(documentId: number, fileName: string): Promise<void> {
  const response = await fetch(`${API_BASE}/documents/${documentId}/download`, {
    credentials: 'same-origin',
  })
  if (!response.ok) {
    throw await responseError(response)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function viewDocument(documentId: number): Promise<void> {
  const preview = window.open('about:blank', '_blank')
  if (!preview) {
    throw new Error('Your browser blocked the document preview. Allow pop-ups for this site and try again.')
  }
  preview.opener = null
  preview.document.title = 'Loading health record…'

  try {
    const response = await fetch(`${API_BASE}/documents/${documentId}/download`, {
      credentials: 'same-origin',
    })
    if (!response.ok) {
      throw await responseError(response)
    }

    const url = URL.createObjectURL(await response.blob())
    preview.location.replace(url)
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (error) {
    preview.close()
    throw error
  }
}

export async function uploadDocument(file: File): Promise<DocumentRecord> {
  const formData = new FormData()
  formData.append('file', file)

  const headers = new Headers()
  const csrfToken = readCsrfToken()
  if (csrfToken) {
    headers.set('X-CSRF-Token', csrfToken)
  }

  return fetch(`${API_BASE}/documents/upload`, {
    method: 'POST',
    headers,
    body: formData,
    credentials: 'same-origin',
  }).then(async (response) => {
    if (!response.ok) {
      throw await responseError(response)
    }
    return response.json() as Promise<DocumentRecord>
  })
}

export async function getDocumentFacts(documentId: number): Promise<MedicalFact[]> {
  return apiFetch<MedicalFact[]>(`/documents/${documentId}/facts`)
}

export async function extractDocumentFacts(documentId: number): Promise<{
  document_id: number
  extracted_fact_count: number
  updated_fact_count: number
  status: string
}> {
  return apiFetch(`/documents/${documentId}/extract`, { method: 'POST' })
}

export async function createManualFact(
  documentId: number,
  payload: {
    fact_type: ManualFactType
    value: string
    event_date: string | null
    page_number: number | null
  },
): Promise<MedicalFact> {
  return apiFetch<MedicalFact>(`/documents/${documentId}/facts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function reviewFact(
  factId: number,
  payload: {
    status: 'accepted' | 'rejected' | 'unreviewed'
    fact_type?: string
    value?: string
    event_date?: string | null
    clear_event_date?: boolean
  },
): Promise<MedicalFact> {
  return apiFetch<MedicalFact>(`/facts/${factId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function getTimeline(): Promise<MedicalFact[]> {
  return apiFetch<MedicalFact[]>('/timeline')
}

export async function getLifestyleProfile(): Promise<LifestyleProfile | null> {
  return apiFetch<LifestyleProfile | null>('/lifestyle')
}

export async function saveLifestyleProfile(profile: LifestyleProfileInput): Promise<LifestyleProfile> {
  return apiFetch<LifestyleProfile>('/lifestyle', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  })
}

export async function askRecordsQuestion(question: string): Promise<RecordsAnswer> {
  return apiFetch<RecordsAnswer>('/records/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
}

export async function searchHealthKnowledge(query: string): Promise<HealthTopic[]> {
  return apiFetch<HealthTopic[]>('/knowledge/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
}
