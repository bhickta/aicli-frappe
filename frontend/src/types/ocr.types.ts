/**
 * OCR Domain Types — TypeScript interfaces for the OCR feature.
 */

// ─── Page Status ─────────────────────────────────────────────────
export type PageStatus = 'Pending' | 'Rendering' | 'Processing' | 'Completed' | 'Failed'
export type JobStatus = 'Queued' | 'Running' | 'Completed' | 'Failed' | 'Paused'

// ─── API Response Types ──────────────────────────────────────────
export interface OcrPage {
  page_number: number
  status: PageStatus
  processing_time: number | null
  error: string | null
}

export interface OcrJobSummary {
  name: string
  pdf_path: string
  model_name: string
  status: JobStatus
  total_pages: number
  completed_pages: number
  failed_pages: number
  started_at: string | null
  completed_at: string | null
}

export interface OcrJobDetail extends OcrJobSummary {
  output_path: string
  rendered_pages: number
  dpi: number
  pages: OcrPage[]
}

export interface StartOcrResponse {
  job_name: string
  status: string
  pdf_path?: string
}

export interface OcrOutputResponse {
  markdown: string
}

// ─── UI State Types ──────────────────────────────────────────────
export interface UploadFormState {
  file: File | null
  model: string
  dpi: number
  maxWorkers: number
}

// ─── Status Color Map ────────────────────────────────────────────
export const STATUS_COLORS: Record<string, string> = {
  Completed: 'var(--success)',
  Running: 'var(--accent)',
  Queued: 'var(--warning, #f59e0b)',
  Failed: 'var(--danger)',
  Paused: 'var(--warning, #f59e0b)',
  Processing: 'var(--accent)',
  Rendering: 'var(--warning, #f59e0b)',
  Pending: 'var(--text-muted)',
}
