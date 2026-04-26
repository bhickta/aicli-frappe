<script setup lang="ts">
/**
 * OcrStudio — Shell component composing upload, job list, and detail sub-components.
 * All logic lives in useOcrStudio composable.
 */
import { useOcrStudio } from '../composables/useOcrStudio'
import OcrUploadForm from './OcrStudio/OcrUploadForm.vue'
import OcrJobList from './OcrStudio/OcrJobList.vue'
import OcrJobDetail from './OcrStudio/OcrJobDetail.vue'

const {
  // State
  jobs, selectedJobName, jobDetail, lastUpdated,
  markdownOutput, showMarkdown,
  selectedModel, maxWorkers,
  availableModels, loadingModels, uploading,
  // Computed
  activeJobs, completedJobs, failedJobs,
  // Methods
  refreshModels, selectJob,
  resumeJob, stopJob, resetJob, deleteJob,
  viewOutput, closeMarkdown, downloadMarkdown,
  statusColor, pdfBasename, progressPercent,
  openNativeUploader,
} = useOcrStudio()

async function handleNativeUpload() {
  try {
    await openNativeUploader()
  } catch (e: any) {
    if (e.message) alert(e.message)
  }
}

async function handleResume(jobName: string) {
  const input = prompt('Enter number of parallel pages (threads):', maxWorkers.value.toString())
  if (input === null) return
  const n = parseInt(input)
  if (isNaN(n) || n < 1) { alert('Invalid number.'); return }
  try { await resumeJob(jobName, n) } catch (e: any) { alert(e.message) }
}

async function handleStop(jobName: string) {
  try { await stopJob(jobName) } catch (e: any) { alert(e.message) }
}

async function handleReset(jobName: string) {
  if (!confirm('Wipe all OCR results and start fresh? (Images will be kept)')) return
  try { await resetJob(jobName) } catch (e: any) { alert(e.message) }
}

async function handleDelete(jobName: string) {
  if (!confirm('Delete this OCR job permanently?')) return
  try { await deleteJob(jobName) } catch (e: any) { alert(e.message) }
}
</script>

<template>
  <div class="ocr-layout">
    <!-- Sidebar -->
    <aside class="ocr-sidebar">
      <OcrUploadForm
        :selected-model="selectedModel"
        :max-workers="maxWorkers"
        :shutdown-after-completion="shutdownAfterCompletion"
        :available-models="availableModels"
        :loading-models="loadingModels"
        :uploading="uploading"
        @update:selected-model="selectedModel = $event"
        @update:max-workers="maxWorkers = $event"
        @update:shutdown-after-completion="shutdownAfterCompletion = $event"
        @native-upload="handleNativeUpload"
        @refresh-models="refreshModels"
      />
      <OcrJobList
        :active-jobs="activeJobs"
        :completed-jobs="completedJobs"
        :failed-jobs="failedJobs"
        :selected-job="selectedJobName"
        :status-color="statusColor"
        :pdf-basename="pdfBasename"
        :progress-percent="progressPercent"
        @select-job="selectJob"
      />
    </aside>

    <!-- Main Panel -->
    <main class="ocr-main">
      <OcrJobDetail
        v-if="jobDetail"
        :job="jobDetail"
        :last-updated="lastUpdated"
        :show-markdown="showMarkdown"
        :markdown-output="markdownOutput"
        :status-color="statusColor"
        :pdf-basename="pdfBasename"
        :progress-percent="progressPercent"
        @resume="handleResume"
        @stop="handleStop"
        @reset="handleReset"
        @delete="handleDelete"
        @view-output="viewOutput"
        @close-markdown="closeMarkdown"
        @download-markdown="downloadMarkdown"
      />

      <div v-else class="ocr-empty-state">
        <div class="icon">🔍</div>
        <p>Select a job from the sidebar, or upload a new ZIP of images to start OCR.</p>
      </div>
    </main>
  </div>
</template>

<style src="../styles/ocr.css"></style>
