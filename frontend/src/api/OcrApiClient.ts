/**
 * OCR API Client — Typed interface to the OCR backend endpoints.
 */
import { frappe } from './FrappeClient'
import { API_BASE } from '../constants/api.constants'
import type {
  OcrJobSummary, OcrJobDetail, OcrOutputResponse, StartOcrResponse,
} from '../types/ocr.types'

export class OcrApiClient {
  async startOcr(
    pdfPath: string, modelName?: string, dpi = 200, maxWorkers = 3,
  ): Promise<StartOcrResponse> {
    return frappe.call('start_ocr', {
      pdf_path: pdfPath, model_name: modelName, dpi, max_workers: maxWorkers,
    })
  }

  async getStatus(jobName: string): Promise<OcrJobDetail> {
    return frappe.call('ocr_status', { job_name: jobName })
  }

  async getOutput(jobName: string): Promise<OcrOutputResponse> {
    return frappe.call('ocr_output', { job_name: jobName })
  }

  async listJobs(): Promise<OcrJobSummary[]> {
    const res = await frappe.call('ocr_jobs')
    return res || []
  }

  async resumeJob(jobName: string, maxWorkers = 3): Promise<StartOcrResponse> {
    return frappe.call('resume_ocr', { job_name: jobName, max_workers: maxWorkers })
  }

  async stopJob(jobName: string): Promise<{ status: string }> {
    return frappe.call('stop_ocr', { job_name: jobName })
  }

  async deleteJob(jobName: string): Promise<{ ok: boolean }> {
    return frappe.call('delete_ocr_job', { job_name: jobName })
  }

  async resetJob(jobName: string): Promise<{ ok: boolean }> {
    return frappe.call('reset_ocr_job', { job_name: jobName })
  }

  async uploadAndOcr(
    file: File, modelName?: string, dpi = 200, maxWorkers = 3,
  ): Promise<StartOcrResponse> {
    const formData = new FormData()
    formData.append('file', file)
    if (modelName) formData.append('model_name', modelName)
    if (dpi) formData.append('dpi', String(dpi))
    if (maxWorkers) formData.append('max_workers', String(maxWorkers))

    const csrfToken = await frappe.getCsrfToken()
    const res = await fetch(`${API_BASE}/api/method/aicli.api.upload_pdf_for_ocr`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'X-Frappe-CSRF-Token': csrfToken,
      },
      body: formData,
    })

    if (!res.ok) throw new Error(`Upload failed: HTTP ${res.status}`)
    const data = await res.json()
    return data.message
  }
}

export const ocrApi = new OcrApiClient()
