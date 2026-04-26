<script setup lang="ts">
/**
 * OcrJobList — Sidebar job list grouped by status.
 */
import type { OcrJobSummary } from '../../types/ocr.types'

defineProps<{
  activeJobs: OcrJobSummary[]
  completedJobs: OcrJobSummary[]
  failedJobs: OcrJobSummary[]
  selectedJob: string | null
  statusColor: (status: string) => string
  pdfBasename: (path: string) => string
  progressPercent: (job: any) => number
}>()

const emit = defineEmits<{
  'select-job': [jobName: string]
}>()
</script>

<template>
  <div class="jobs-section">
    <h4>Jobs</h4>

    <!-- Active -->
    <div v-if="activeJobs.length" class="job-group">
      <div class="group-label">🔄 Active</div>
      <div
        v-for="job in activeJobs" :key="job.name"
        class="job-card" :class="{ selected: selectedJob === job.name }"
        @click="emit('select-job', job.name)"
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

    <!-- Needs Attention -->
    <div v-if="failedJobs.length" class="job-group">
      <div class="group-label">⚠️ Needs Attention</div>
      <div
        v-for="job in failedJobs" :key="job.name"
        class="job-card" :class="{ selected: selectedJob === job.name }"
        @click="emit('select-job', job.name)"
      >
        <div class="job-name">{{ pdfBasename(job.pdf_path) }}</div>
        <div class="job-meta">
          <span class="status-dot" :style="{ background: statusColor(job.status) }"></span>
          {{ job.status }} — {{ job.completed_pages }}/{{ job.total_pages }}
          <span v-if="job.failed_pages" class="error-count">{{ job.failed_pages }} errors</span>
        </div>
      </div>
    </div>

    <!-- Completed -->
    <div v-if="completedJobs.length" class="job-group">
      <div class="group-label">✅ Completed</div>
      <div
        v-for="job in completedJobs" :key="job.name"
        class="job-card" :class="{ selected: selectedJob === job.name }"
        @click="emit('select-job', job.name)"
      >
        <div class="job-name">{{ pdfBasename(job.pdf_path) }}</div>
        <div class="job-meta">
          <span class="status-dot" :style="{ background: statusColor(job.status) }"></span>
          {{ job.total_pages }} pages • {{ job.model_name }}
        </div>
      </div>
    </div>

    <!-- Empty -->
    <div v-if="!activeJobs.length && !failedJobs.length && !completedJobs.length" class="empty-jobs">
      <p>No OCR jobs yet. Upload a PDF to get started.</p>
    </div>
  </div>
</template>
