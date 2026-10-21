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
  document_id: number
  fact_type: string
  value: string
  status: string
  confidence: number
  source_excerpt?: string | null
  page_number?: number | null
  event_date?: string | null
  numeric_value?: number | null
  unit?: string | null
  created_at: string
}

export type ManualFactType =
  | 'diagnosis'
  | 'symptom'
  | 'medication'
  | 'allergy'
  | 'lab'
  | 'procedure'
  | 'medical_event'
  | 'provider'
  | 'lifestyle_activity'
  | 'lifestyle_sleep'
  | 'lifestyle_diet'
  | 'lifestyle_tobacco'
  | 'lifestyle_alcohol'

export type RecordCitation = {
  document_id: number
  file_name: string
  page_number: number | null
  event_date: string | null
  excerpt: string | null
}

export type RecordsAnswer = {
  answer: string
  insufficient_evidence: boolean
  possible_conflict: boolean
  citations: RecordCitation[]
}

export type HealthTopic = {
  title: string
  summary: string
  url: string
  source: string
}

export type ActivityFrequency = 'rarely' | '1-2 days/week' | '3-4 days/week' | '5+ days/week'
export type TobaccoUse = 'never' | 'former' | 'current' | 'prefer_not_to_say'
export type AlcoholFrequency = 'never' | 'occasionally' | 'weekly' | 'daily' | 'prefer_not_to_say'

export type LifestyleProfileInput = {
  activity_frequency: ActivityFrequency | null
  diet_notes: string | null
  sleep_hours: number | null
  tobacco_use: TobaccoUse | null
  alcohol_frequency: AlcoholFrequency | null
  notes: string | null
}

export type LifestyleProfile = LifestyleProfileInput & {
  updated_at: string
}
