import type { DocumentRecord, MedicalFact, User } from '../types'

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
    const text = await response.text()
    throw new Error(text || 'Unable to download this document')
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
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

export async function reviewFact(factId: number, status: 'accepted' | 'rejected' | 'unreviewed'): Promise<MedicalFact> {
  return apiFetch<MedicalFact>(`/facts/${factId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

export async function getTimeline(): Promise<MedicalFact[]> {
  return apiFetch<MedicalFact[]>('/timeline')
}
