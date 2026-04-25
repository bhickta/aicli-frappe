<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { ocrApi } from '../api/OcrApiClient'
import { settingsApi } from '../api/SettingsApiClient'

// ─── State ───────────────────────────────────────────────────────
const jobs = ref<any[]>([])
const selectedJob = ref<any>(null)
const jobDetail = ref<any>(null)
const markdownOutput = ref('')
const showMarkdown = ref(false)

// Upload form
const selectedFile = ref<File | null>(null)
const selectedModel = ref('')
const dpi = ref(200)
const availableModels = ref<string[]>([])
const loadingModels = ref(false)
const uploading = ref(false)

// Polling
let pollInterval: any = null

// ─── Computed ────────────────────────────────────────────────────
const activeJobs = computed(() =>
  jobs.value.filter(j => j.status === 'Running' || j.status === 'Queued')
)

const completedJobs = computed(() =>
  jobs.value.filter(j => j.status === 'Completed')
)

const failedJobs = computed(() =>
  jobs.value.filter(j => j.status === 'Failed' || j.status === 'Paused')
)

// ─── Methods ─────────────────────────────────────────────────────
async function loadJobs() {
  try {
    jobs.value = await ocrApi.listJobs()
  } catch (e) {
    console.error('Failed to load OCR jobs:', e)
  }
}

async function refreshModels() {
  loadingModels.value = true
  try {
    const res = await settingsApi.fetchModels()
    availableModels.value = res?.models || []
    if (availableModels.value.length > 0 && !selectedModel.value) {
      // Pick a vision model if available
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

function onFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    selectedFile.value = input.files[0]
  }
}

async function uploadAndStart() {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const result = await ocrApi.uploadAndOcr(selectedFile.value, selectedModel.value, dpi.value)
    selectedFile.value = null
    // Reset file input
    const input = document.getElementById('ocr-file-input') as HTMLInputElement
    if (input) input.value = ''
    await loadJobs()
    // Auto-select the new job
    if (result?.job_name) {
      await selectJob(result.job_name)
    }
  } catch (e: any) {
    alert('Upload failed: ' + e.message)
  } finally {
    uploading.value = false
  }
}

async function selectJob(jobName: string) {
  try {
    jobDetail.value = await ocrApi.getStatus(jobName)
    selectedJob.value = jobName
    showMarkdown.value = false
    markdownOutput.value = ''
  } catch (e) {
    console.error('Failed to get job status:', e)
  }
}

async function viewOutput() {
  if (!selectedJob.value) return
  try {
    const res = await ocrApi.getOutput(selectedJob.value)
    markdownOutput.value = res?.markdown || '(No output yet)'
    showMarkdown.value = true
  } catch (e) {
    console.error('Failed to get output:', e)
  }
}

async function resumeJob(jobName: string) {
  try {
    await ocrApi.resumeJob(jobName)
    await loadJobs()
    if (selectedJob.value === jobName) {
      jobDetail.value = await ocrApi.getStatus(jobName)
    }
  } catch (e: any) {
    alert('Resume failed: ' + e.message)
  }
}

async function deleteJob(jobName: string) {
  if (!confirm('Delete this OCR job permanently?')) return
  try {
    await ocrApi.deleteJob(jobName)
    if (selectedJob.value === jobName) {
      selectedJob.value = null
      jobDetail.value = null
    }
    await loadJobs()
  } catch (e: any) {
    alert('Delete failed: ' + e.message)
  }
}

function downloadMarkdown() {
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

function statusColor(status: string) {
  const map: Record<string, string> = {
    Completed: 'var(--success)',
    Running: 'var(--accent)',
    Queued: 'var(--warning, #f59e0b)',
    Failed: 'var(--danger)',
    Paused: 'var(--warning, #f59e0b)',
    Processing: 'var(--accent)',
    Pending: 'var(--text-muted)',
  }
  return map[status] || 'var(--text-muted)'
}

function pdfBasename(path: string) {
  return path?.split('/').pop() || path
}

function progressPercent(job: any) {
  if (!job?.total_pages) return 0
  return Math.round((job.completed_pages / job.total_pages) * 100)
}

// ─── Polling for active jobs ─────────────────────────────────────
async function poll() {
  await loadJobs()
  if (selectedJob.value && jobDetail.value?.status !== 'Completed') {
    try {
      jobDetail.value = await ocrApi.getStatus(selectedJob.value)
    } catch { /* ignore */ }
  }
}

onMounted(async () => {
  await Promise.all([loadJobs(), refreshModels()])
  pollInterval = setInterval(poll, 3000)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})
</script>

<template>
  <div class="ocr-layout">
    <!-- ─── Left Panel: Upload + Job List ──────────────────────── -->
    <aside class="ocr-sidebar">
      <div class="upload-section">
        <h3>📄 PDF → Markdown OCR</h3>
        <p class="subtitle">Upload a PDF and extract text using a local LLM vision model.</p>

        <div class="upload-form">
          <div class="form-group">
            <label>PDF File</label>
            <input
              id="ocr-file-input"
              type="file"
              accept=".pdf"
              @change="onFileSelect"
              class="file-input"
            />
          </div>

          <div class="form-group">
            <label>Vision Model</label>
            <div class="model-select-row">
              <select v-model="selectedModel" class="form-select">
                <option disabled value="">Select model…</option>
                <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
                <option v-if="availableModels.length === 0" disabled>No models found</option>
              </select>
              <button @click="refreshModels" class="btn-icon" :disabled="loadingModels" title="Refresh">
                {{ loadingModels ? '⏳' : '🔄' }}
              </button>
            </div>
          </div>

          <div class="form-group">
            <label>DPI (higher = better quality, slower)</label>
            <input type="number" v-model.number="dpi" min="72" max="600" step="50" class="form-input" />
          </div>

          <button
            class="btn btn-primary upload-btn"
            @click="uploadAndStart"
            :disabled="!selectedFile || uploading"
          >
            {{ uploading ? '⏳ Uploading…' : '🚀 Upload & Start OCR' }}
          </button>
        </div>
      </div>

      <div class="jobs-section">
        <h4>Jobs</h4>

        <div v-if="activeJobs.length" class="job-group">
          <div class="group-label">🔄 Active</div>
          <div
            v-for="job in activeJobs"
            :key="job.name"
            class="job-card"
            :class="{ selected: selectedJob === job.name }"
            @click="selectJob(job.name)"
          >
            <div class="job-name">{{ pdfBasename(job.pdf_path) }}</div>
            <div class="job-meta">
              <span class="status-dot" :style="{ background: statusColor(job.status) }"></span>
              {{ job.status }} — {{ job.completed_pages }}/{{ job.total_pages }}
            </div>
            <div class="progress-bar-mini">
              <div class="fill" :style="{ width: progressPercent(job) + '%' }"></div>
            </div>
          </div>
        </div>

        <div v-if="failedJobs.length" class="job-group">
          <div class="group-label">⚠️ Needs Attention</div>
          <div
            v-for="job in failedJobs"
            :key="job.name"
            class="job-card"
            :class="{ selected: selectedJob === job.name }"
            @click="selectJob(job.name)"
          >
            <div class="job-name">{{ pdfBasename(job.pdf_path) }}</div>
            <div class="job-meta">
              <span class="status-dot" :style="{ background: statusColor(job.status) }"></span>
              {{ job.status }} — {{ job.completed_pages }}/{{ job.total_pages }}
              <span v-if="job.failed_pages" class="error-count">{{ job.failed_pages }} errors</span>
            </div>
          </div>
        </div>

        <div v-if="completedJobs.length" class="job-group">
          <div class="group-label">✅ Completed</div>
          <div
            v-for="job in completedJobs"
            :key="job.name"
            class="job-card"
            :class="{ selected: selectedJob === job.name }"
            @click="selectJob(job.name)"
          >
            <div class="job-name">{{ pdfBasename(job.pdf_path) }}</div>
            <div class="job-meta">
              <span class="status-dot" :style="{ background: statusColor(job.status) }"></span>
              {{ job.total_pages }} pages • {{ job.model_name }}
            </div>
          </div>
        </div>

        <div v-if="!jobs.length" class="empty-jobs">
          <p>No OCR jobs yet. Upload a PDF to get started.</p>
        </div>
      </div>
    </aside>

    <!-- ─── Main Panel: Job Detail / Output ────────────────────── -->
    <main class="ocr-main">
      <template v-if="jobDetail">
        <!-- Header -->
        <div class="detail-header">
          <div>
            <h2>{{ pdfBasename(jobDetail.pdf_path) }}</h2>
            <div class="detail-meta">
              <span class="status-badge" :style="{ background: statusColor(jobDetail.status) }">
                {{ jobDetail.status }}
              </span>
              <span>{{ jobDetail.completed_pages }} / {{ jobDetail.total_pages }} pages</span>
              <span v-if="jobDetail.failed_pages" class="error-tag">{{ jobDetail.failed_pages }} failed</span>
              <span class="model-tag">🤖 {{ jobDetail.model_name }}</span>
            </div>
          </div>
          <div class="detail-actions">
            <button
              v-if="['Paused', 'Failed', 'Queued'].includes(jobDetail.status)"
              class="btn btn-secondary"
              @click="resumeJob(jobDetail.name)"
            >
              ▶ Resume
            </button>
            <button
              v-if="jobDetail.completed_pages > 0"
              class="btn btn-secondary"
              @click="viewOutput"
            >
              📖 View Markdown
            </button>
            <button class="btn btn-ghost btn-danger" @click="deleteJob(jobDetail.name)">
              🗑️ Delete
            </button>
          </div>
        </div>

        <!-- Progress bar -->
        <div class="progress-section">
          <div class="progress-bar-lg">
            <div
              class="fill"
              :style="{ width: progressPercent(jobDetail) + '%' }"
            ></div>
          </div>
          <span class="progress-label">{{ progressPercent(jobDetail) }}%</span>
        </div>

        <!-- Markdown Output View -->
        <div v-if="showMarkdown" class="markdown-viewer">
          <div class="viewer-header">
            <h3>📝 Markdown Output</h3>
            <div class="viewer-actions">
              <button class="btn btn-secondary" @click="downloadMarkdown">⬇️ Download .md</button>
              <button class="btn btn-ghost" @click="showMarkdown = false">✕ Close</button>
            </div>
          </div>
          <pre class="markdown-content">{{ markdownOutput }}</pre>
        </div>

        <!-- Page Grid -->
        <div v-else class="pages-grid">
          <div
            v-for="page in jobDetail.pages"
            :key="page.page_number"
            class="page-card"
            :class="page.status.toLowerCase()"
          >
            <div class="page-num">{{ page.page_number }}</div>
            <div class="page-status">
              <span class="status-dot-sm" :style="{ background: statusColor(page.status) }"></span>
              {{ page.status }}
            </div>
            <div v-if="page.processing_time" class="page-time">
              {{ page.processing_time.toFixed(1) }}s
            </div>
            <div v-if="page.error" class="page-error" :title="page.error">⚠</div>
          </div>
        </div>
      </template>

      <!-- Empty State -->
      <div v-else class="empty-state">
        <div class="icon">🔍</div>
        <p>Select a job from the sidebar, or upload a new PDF to start OCR.</p>
      </div>
    </main>
  </div>
</template>

<style scoped>
.ocr-layout {
  display: flex;
  height: 100%;
  width: 100%;
  overflow: hidden;
}

/* ─── Sidebar ──────────────────────────────────────────────────── */
.ocr-sidebar {
  width: 360px;
  min-width: 360px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.upload-section {
  padding: 20px;
  border-bottom: 1px solid var(--border);
}

.upload-section h3 {
  margin: 0 0 4px;
  font-size: 16px;
}

.subtitle {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0 0 16px;
}

.upload-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-group label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.file-input {
  background: var(--bg-input, rgba(255,255,255,0.05));
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 12px;
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
}
.file-input:hover {
  border-color: var(--accent);
}

.model-select-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.form-select {
  flex: 1;
  background: var(--bg-input, rgba(255,255,255,0.05));
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
  outline: none;
}
.form-select:focus { border-color: var(--accent); }

.form-input {
  background: var(--bg-input, rgba(255,255,255,0.05));
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
  outline: none;
  width: 100%;
}

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  opacity: 0.7;
}
.btn-icon:hover { opacity: 1; }

.upload-btn {
  margin-top: 4px;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
}

/* ─── Jobs List ────────────────────────────────────────────────── */
.jobs-section {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.jobs-section h4 {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin: 0 0 12px;
}

.job-group { margin-bottom: 16px; }

.group-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
  padding-left: 4px;
}

.job-card {
  background: var(--bg-body);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.job-card:hover { border-color: var(--accent); background: rgba(99,102,241,0.05); }
.job-card.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }

.job-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.job-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.error-count {
  color: var(--danger);
  font-weight: 600;
}

.progress-bar-mini {
  height: 3px;
  background: rgba(255,255,255,0.08);
  border-radius: 2px;
  margin-top: 6px;
  overflow: hidden;
}
.progress-bar-mini .fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.empty-jobs {
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  padding: 24px 0;
}

/* ─── Main Panel ───────────────────────────────────────────────── */
.ocr-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 24px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.detail-header h2 {
  font-size: 20px;
  margin: 0 0 6px;
}

.detail-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--text-muted);
}

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  text-transform: uppercase;
}

.error-tag {
  color: var(--danger);
  font-weight: 600;
}

.model-tag {
  background: rgba(255,255,255,0.06);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.detail-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* Progress */
.progress-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.progress-bar-lg {
  flex: 1;
  height: 8px;
  background: rgba(255,255,255,0.08);
  border-radius: 4px;
  overflow: hidden;
}
.progress-bar-lg .fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), #818cf8);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
  min-width: 40px;
  text-align: right;
}

/* ─── Page Grid ────────────────────────────────────────────────── */
.pages-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 8px;
}

.page-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 8px;
  text-align: center;
  position: relative;
  transition: all 0.15s;
}
.page-card.completed { border-color: var(--success); background: rgba(16,185,129,0.06); }
.page-card.processing { border-color: var(--accent); background: rgba(99,102,241,0.08); animation: pulse-border 1.5s infinite; }
.page-card.failed { border-color: var(--danger); background: rgba(239,68,68,0.06); }

@keyframes pulse-border {
  0%, 100% { box-shadow: 0 0 0 0 rgba(99,102,241,0.3); }
  50% { box-shadow: 0 0 0 4px rgba(99,102,241,0.1); }
}

.page-num {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.page-status {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.status-dot-sm {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.page-time {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
}

.page-error {
  position: absolute;
  top: 4px;
  right: 6px;
  font-size: 12px;
  cursor: help;
}

/* ─── Markdown Viewer ──────────────────────────────────────────── */
.markdown-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.viewer-header h3 { margin: 0; font-size: 16px; }

.viewer-actions {
  display: flex;
  gap: 8px;
}

.markdown-content {
  flex: 1;
  background: var(--bg-body);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  overflow-y: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* ─── Empty state ──────────────────────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--text-muted);
}
.empty-state .icon { font-size: 48px; margin-bottom: 16px; }
.empty-state p { font-size: 14px; }

/* ─── Shared button styles ─────────────────────────────────────── */
.btn {
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 14px;
  transition: all 0.15s;
}
.btn-primary {
  background: var(--accent);
  color: white;
}
.btn-primary:hover { filter: brightness(1.15); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  background: rgba(255,255,255,0.08);
  color: var(--text-primary);
  border: 1px solid var(--border);
}
.btn-secondary:hover { background: rgba(255,255,255,0.12); }

.btn-ghost {
  background: transparent;
  color: var(--text-muted);
}
.btn-ghost:hover { color: var(--text-primary); }
.btn-danger { color: var(--danger); }
</style>
