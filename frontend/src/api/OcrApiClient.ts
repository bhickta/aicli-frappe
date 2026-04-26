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
}

export const ocrApi = new OcrApiClient()
