import { frappe } from './FrappeClient'
import { API_BASE } from '../constants/api.constants'

export class OcrApiClient {
  async startOcr(pdfPath: string, modelName?: string, dpi?: number, maxWorkers?: number): Promise<any> {
    return frappe.call('start_ocr', { pdf_path: pdfPath, model_name: modelName, dpi: dpi || 200, max_workers: maxWorkers || 3 })
  }

  async getStatus(jobName: string): Promise<any> {
    return frappe.call('ocr_status', { job_name: jobName })
  }

  async getOutput(jobName: string): Promise<any> {
    return frappe.call('ocr_output', { job_name: jobName })
  }

  async listJobs(): Promise<any[]> {
    const res = await frappe.call('ocr_jobs')
    return res || []
  }

  async resumeJob(jobName: string, maxWorkers?: number): Promise<any> {
    return frappe.call('resume_ocr', { job_name: jobName, max_workers: maxWorkers || 3 })
  }

  async deleteJob(jobName: string): Promise<any> {
    return frappe.call('delete_ocr_job', { job_name: jobName })
  }

  async uploadAndOcr(file: File, modelName?: string, dpi?: number, maxWorkers?: number): Promise<any> {
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
