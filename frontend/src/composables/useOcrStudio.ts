/**
 * useOcrStudio — Composable encapsulating all OCR Studio state and logic.
 *
 * Extracts reactive state, computed properties, and methods from the
 * monolithic OcrStudio.vue component for reusability and testability.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ocrApi } from '../api/OcrApiClient'
import { settingsApi } from '../api/SettingsApiClient'
import type {
  OcrJobSummary, OcrJobDetail, JobStatus, STATUS_COLORS,
} from '../types/ocr.types'
import { STATUS_COLORS as statusColorMap } from '../types/ocr.types'

const POLL_INTERVAL_MS = 3000

export function useOcrStudio() {
  // ─── Reactive State ──────────────────────────────────────────
  const jobs = ref<OcrJobSummary[]>([])
  const selectedJobName = ref<string | null>(null)
  const jobDetail = ref<OcrJobDetail | null>(null)
  const lastUpdated = ref(new Date().toLocaleTimeString())
  const markdownOutput = ref('')
  const showMarkdown = ref(false)

  // Upload form
  const selectedModel = ref('')
  const maxWorkers = ref(24)
  const shutdownAfterCompletion = ref(false)
  const availableModels = ref<string[]>([])
  const loadingModels = ref(false)
  const uploading = ref(false)

  let pollHandle: ReturnType<typeof setInterval> | null = null

  // ─── Computed ────────────────────────────────────────────────
  const activeJobs = computed(() =>
    jobs.value.filter(j => j.status === 'Running' || j.status === 'Queued')
  )
  const completedJobs = computed(() =>
    jobs.value.filter(j => j.status === 'Completed')
  )
  const failedJobs = computed(() =>
    jobs.value.filter(j => j.status === 'Failed' || j.status === 'Paused')
  )

  // ─── Data Loading ────────────────────────────────────────────
  async function loadJobs(): Promise<void> {
    try {
      jobs.value = await ocrApi.listJobs()
    } catch (e) {
      console.error('Failed to load OCR jobs:', e)
    }
  }

  async function refreshModels(): Promise<void> {
    loadingModels.value = true
    try {
      const res = await settingsApi.fetchModels()
      availableModels.value = res?.models || []
      if (availableModels.value.length > 0 && !selectedModel.value) {
        const vision = availableModels.value.find(m =>
          m.includes('vision') || m.includes('gemma') || m.includes('qwen')
        )
        selectedModel.value = vision || availableModels.value[0]
      }
    } catch (e) {
      console.error('Failed to fetch models:', e)
    } finally {
      loadingModels.value = false
    }
  }

  // ─── Job Actions ─────────────────────────────────────────────
  async function selectJob(jobName: string): Promise<void> {
    try {
      jobDetail.value = await ocrApi.getStatus(jobName)
      selectedJobName.value = jobName
      showMarkdown.value = false
      markdownOutput.value = ''
    } catch (e) {
      console.error('Failed to get job status:', e)
    }
  }

  async function openNativeUploader(): Promise<void> {
    return new Promise((resolve, reject) => {
      // @ts-ignore
      if (!window.frappe) {
        reject(new Error('Frappe context not found. Please ensure you are running inside Frappe Desk.'))
        return
      }

      // @ts-ignore
      const d = new window.frappe.ui.FileUploader({
        make_attachments: 0,
        on_success: async (fileDoc: any) => {
          if (fileDoc.file_url) {
            uploading.value = true
            try {
              const result = await ocrApi.startZipOcr(
                fileDoc.file_url, selectedModel.value, maxWorkers.value, shutdownAfterCompletion.value
              )
              await loadJobs()
              if (result?.job_name) {
                await selectJob(result.job_name)
              }
              resolve()
            } catch (e: any) {
              console.error('OCR Start failed:', e)
              reject(e)
            } finally {
              uploading.value = false
            }
          }
        }
      })
    })
  }

  async function resumeJob(jobName: string, workers: number): Promise<void> {
    // If currently running, stop the old worker first
    if (jobDetail.value?.status === 'Running') {
      await ocrApi.stopJob(jobName)
      await new Promise(r => setTimeout(r, 2000))
    }
    await ocrApi.resumeJob(jobName, workers)
    await loadJobs()
    if (selectedJobName.value === jobName) {
      jobDetail.value = await ocrApi.getStatus(jobName)
    }
  }

  async function stopJob(jobName: string): Promise<void> {
    await ocrApi.stopJob(jobName)
    await loadJobs()
    if (selectedJobName.value === jobName) {
      jobDetail.value = await ocrApi.getStatus(jobName)
    }
  }

  async function resetJob(jobName: string): Promise<void> {
    await ocrApi.resetJob(jobName)
    await loadJobs()
    if (selectedJobName.value === jobName) {
      jobDetail.value = await ocrApi.getStatus(jobName)
    }
  }

  async function deleteJob(jobName: string): Promise<void> {
    await ocrApi.deleteJob(jobName)
    if (selectedJobName.value === jobName) {
      selectedJobName.value = null
      jobDetail.value = null
    }
    await loadJobs()
  }

  async function viewOutput(): Promise<void> {
    if (!selectedJobName.value) return
    try {
      const res = await ocrApi.getOutput(selectedJobName.value)
      markdownOutput.value = res?.markdown || '(No output yet)'
      showMarkdown.value = true
    } catch (e) {
      console.error('Failed to get output:', e)
    }
  }

  function closeMarkdown(): void {
    showMarkdown.value = false
  }

  function downloadMarkdown(): void {
    if (!markdownOutput.value || !jobDetail.value) return
    const blob = new Blob([markdownOutput.value], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const pdfName = jobDetail.value.pdf_path?.split('/').pop()?.replace('.pdf', '') || 'ocr_output'
    a.download = `${pdfName}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  function statusColor(status: string): string {
    return statusColorMap[status] || 'var(--text-muted)'
  }

  function pdfBasename(path: string): string {
    return path?.split('/').pop() || path
  }

  function progressPercent(job: { total_pages?: number; completed_pages?: number } | null): number {
    if (!job?.total_pages) return 0
    return Math.round(((job.completed_pages || 0) / job.total_pages) * 100)
  }

  // ─── Polling ─────────────────────────────────────────────────
  async function poll(): Promise<void> {
    await loadJobs()
    if (selectedJobName.value && jobDetail.value?.status !== 'Completed') {
      try {
        jobDetail.value = await ocrApi.getStatus(selectedJobName.value)
        lastUpdated.value = new Date().toLocaleTimeString()
      } catch { /* ignore polling errors */ }
    }
  }

  function startPolling(): void {
    pollHandle = setInterval(poll, POLL_INTERVAL_MS)
  }

  function stopPolling(): void {
    if (pollHandle) {
      clearInterval(pollHandle)
      pollHandle = null
    }
  }

  // ─── Lifecycle ───────────────────────────────────────────────
  onMounted(async () => {
    await Promise.all([loadJobs(), refreshModels()])
    startPolling()
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    // State
    jobs, selectedJobName, jobDetail, lastUpdated,
    markdownOutput, showMarkdown,
    selectedModel, maxWorkers, shutdownAfterCompletion,
    availableModels, loadingModels, uploading,
    // Computed
    activeJobs, completedJobs, failedJobs,
    // Methods
    loadJobs, refreshModels, selectJob, openNativeUploader,
    resumeJob, stopJob, resetJob, deleteJob,
    viewOutput, closeMarkdown, downloadMarkdown,
    statusColor, pdfBasename, progressPercent,
  }
}
