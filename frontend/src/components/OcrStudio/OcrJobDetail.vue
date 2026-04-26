<script setup lang="ts">
/**
 * OcrJobDetail — Main panel showing job detail, actions, progress, and content.
 */
import type { OcrJobDetail as JobDetail } from '../../types/ocr.types'
import OcrPageGrid from './OcrPageGrid.vue'
import OcrErrorLog from './OcrErrorLog.vue'
import OcrMarkdownViewer from './OcrMarkdownViewer.vue'

defineProps<{
  job: JobDetail
  lastUpdated: string
  showMarkdown: boolean
  markdownOutput: string
  statusColor: (status: string) => string
  pdfBasename: (path: string) => string
  progressPercent: (job: any) => number
}>()

const emit = defineEmits<{
  resume: [jobName: string]
  stop: [jobName: string]
  reset: [jobName: string]
  delete: [jobName: string]
  'view-output': []
  'close-markdown': []
  'download-markdown': []
}>()
</script>

<template>
  <!-- Header -->
  <div class="detail-header">
    <div>
      <h2>{{ pdfBasename(job.pdf_path) }}</h2>
      <div class="detail-meta">
        <span class="status-badge" :style="{ background: statusColor(job.status) }">
          {{ job.status }}
        </span>
        <span class="count-badge">📸 {{ job.rendered_pages }} / {{ job.total_pages }} images</span>
        <span class="count-badge">🧠 {{ job.completed_pages }} / {{ job.total_pages }} ocr</span>
        <span v-if="job.failed_pages" class="error-tag">{{ job.failed_pages }} failed</span>
        <span class="model-tag">🤖 {{ job.model_name }}</span>
        <span class="last-updated">🕒 {{ lastUpdated }}</span>
      </div>
    </div>
    <div class="detail-actions">
      <button
        v-if="['Paused', 'Failed', 'Queued', 'Running'].includes(job.status)"
        class="btn btn-secondary" @click="emit('resume', job.name)"
      >
        ▶ {{ job.status === 'Running' ? 'Force Resume' : 'Resume' }}
      </button>
      <button
        v-if="job.status === 'Running'"
        class="btn btn-danger" @click="emit('stop', job.name)"
      >
        ⏹ Force Stop
      </button>
      <button
        v-if="job.completed_pages > 0"
        class="btn btn-secondary" @click="emit('view-output')"
      >
        📖 View Markdown
      </button>
      <button
        v-if="['Paused', 'Failed', 'Completed'].includes(job.status)"
        class="btn btn-ghost" @click="emit('reset', job.name)"
        title="Wipe OCR progress and start fresh"
      >
        🔄 Reset
      </button>
      <button class="btn btn-ghost btn-danger-text" @click="emit('delete', job.name)">
        🗑️ Delete
      </button>
    </div>
  </div>

  <!-- Progress bar -->
  <div class="progress-section">
    <div class="progress-bar-lg">
      <div class="fill" :style="{ width: progressPercent(job) + '%' }"></div>
    </div>
    <span class="progress-label">{{ progressPercent(job) }}%</span>
  </div>

  <!-- Markdown Output View -->
  <OcrMarkdownViewer
    v-if="showMarkdown"
    :markdown="markdownOutput"
    @close="emit('close-markdown')"
    @download="emit('download-markdown')"
  />

  <!-- Page Grid + Errors -->
  <template v-else>
    <OcrPageGrid :pages="job.pages" :status-color="statusColor" />
    <OcrErrorLog v-if="job.failed_pages > 0" :pages="job.pages" />
  </template>
</template>
