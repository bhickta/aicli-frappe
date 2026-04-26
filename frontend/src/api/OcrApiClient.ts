/**
 * OCR API Client — Typed interface to the OCR backend endpoints.
 */
import { frappe } from './FrappeClient'
import { API_BASE } from '../constants/api.constants'
import type {
  OcrJobSummary, OcrJobDetail, OcrOutputResponse, StartOcrResponse,
} from '../types/ocr.types'

export class OcrApiClient {
  async startZipOcr(
    fileUrl: string, modelName?: string, maxWorkers = 3,
  ): Promise<StartOcrResponse> {
    return frappe.call('start_zip_ocr', {
      file_url: fileUrl, model_name: modelName, max_workers: maxWorkers,
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

  /**
   * Uploads a file using Frappe's native file handler and then starts the OCR job.
   */
  async uploadAndOcr(
    file: File, modelName?: string, maxWorkers = 3,
  ): Promise<StartOcrResponse> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('is_private', '0')
    formData.append('folder', 'Home/Attachments')

    const csrfToken = await frappe.getCsrfToken()
    // Use Frappe's native upload handler
    const uploadRes = await fetch(`${API_BASE}/api/method/frappe.handler.upload_file`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'X-Frappe-CSRF-Token': csrfToken,
      },
      body: formData,
    })

    if (!uploadRes.ok) {
      const errText = await uploadRes.text()
      throw new Error(`Upload failed: HTTP ${uploadRes.status} - ${errText}`)
    }
    
    const uploadData = await uploadRes.json()
    const fileUrl = uploadData.message.file_url

    if (!fileUrl) throw new Error('Upload succeeded but no file_url returned.')

    // Now start the OCR job using the file URL
    return this.startZipOcr(fileUrl, modelName, maxWorkers)
  }
}

export const ocrApi = new OcrApiClient()
