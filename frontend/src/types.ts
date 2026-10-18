export type User = {
  id: number
  email: string
  full_name: string
}

export type DocumentRecord = {
  id: number
  file_name: string
  content_type: string
  status: string
  preview_text?: string | null
  document_type?: string | null
  document_date?: string | null
  provider_name?: string | null
  uploaded_at: string
}

export type MedicalFact = {
  id: number
  fact_type: string
  value: string
  status: string
  confidence: number
  source_excerpt?: string | null
  page_number?: number | null
  created_at: string
}
