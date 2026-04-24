import { API_BASE } from '../constants/api.constants'
import { frappe } from './FrappeClient'

export class AnalyzeApiClient {
  async fetchStatus(): Promise<any> {
    return frappe.call('get_pipeline_status')
  }

  async fetchPdfs(): Promise<any[]> {
    return frappe.call('get_pdfs')
  }

  async fetchPages(pdf: { id: string | number }): Promise<any[]> {
    return frappe.call('get_pages', { pdf_file: pdf.id })
  }

  async fetchAnswers(pdf: { id: string | number }): Promise<any[]> {
    return frappe.call('get_answers', { pdf_file: pdf.id })
  }

  async fetchDimensions(answerId: string | number): Promise<any[]> {
    return frappe.call('get_dimensions', { answer_id: answerId })
  }

  async fetchAggregations(): Promise<any[]> {
    const data = await frappe.call('get_aggregations')
    if (!data) return []
    if (Array.isArray(data)) return data
    return Object.keys(data).map(k => ({ dimension_name: k, ...data[k] }))
  }

  async resetPipeline(step: number): Promise<any> {
    return frappe.call('reset_pipeline', { step })
  }

  async retryErrors(): Promise<any> {
    return frappe.call('retry_errors')
  }

  async runPipeline(config: Record<string, unknown>): Promise<any> {
    return frappe.call('run_analyze', config)
  }

  async stopPipeline(): Promise<any> {
    return frappe.call('stop_pipeline')
  }

  async fetchOrchestratorStatus(): Promise<any> {
    return frappe.call('get_pipeline_status')
  }

  async deletePdf(pdfFile: string): Promise<any> {
    return frappe.call('delete_pdf', { pdf_file: pdfFile })
  }

  async uploadPdfs(files: FileList): Promise<any> {
    const formData = new FormData()
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i])
    }
    
    // For file uploads, we bypass FrappeClient to use FormData
    const res = await fetch(`${API_BASE}/api/method/aicli.api.upload_pdfs`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json'
      },
      body: formData,
    })
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }
    return res.json()
  }

  createStream(): EventSource {
    // Return a dummy stream for now, UI will poll status via orchestrator instead
    return new EventSource(`${API_BASE}/api/method/aicli.api.stream_status`)
  }

  imageUrl(pdfFile: string, pageNumber: number): string {
    const paddedPage = String(pageNumber).padStart(4, '0')
    const pdfName = pdfFile.replace(/\.pdf$/i, '')
    // Update to correct path based on Frappe's file routing, assuming public/files/aicli_data
    return `${API_BASE}/files/aicli_data/images/${encodeURIComponent(pdfName)}/page_${paddedPage}.png`
  }
}

export const analyzeApi = new AnalyzeApiClient()
