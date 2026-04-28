<template>
  <div class="workspace-layout">
    <AudioSidebar 
      v-model:activeTab="activeTab" 
      :jobs="jobs" 
      :selectedJob="selectedJob"
      @select-job="selectJob"
    />

    <main class="main-content">
      <div class="top-bar">
        <h2>{{ tabTitle }}</h2>
        <div class="top-bar-actions" v-if="selectedJob">
          <span class="job-id-badge">{{ selectedJob.slice(0, 8) }}…</span>
          <button 
            v-if="jobStatus && jobStatus.status === 'Running'" 
            class="btn btn-danger btn-sm" 
            @click="stopCurrentJob"
          >
            ⏹ Stop
          </button>
          <button class="btn btn-ghost btn-sm" @click="deleteCurrentJob">
            🗑 Delete
          </button>
        </div>
      </div>

      <div class="content-body" style="padding: 24px; max-width: 960px;">
        <!-- Upload Tab -->
        <AudioUpload 
          v-if="activeTab === 'upload'"
          :pipelineRunning="isPipelineRunning"
          @job-created="onJobCreated"
          @stop="stopCurrentJob"
        />

        <!-- Transcription Tab -->
        <TranscriptionView 
          v-if="activeTab === 'tracks'"
          :tracks="tracks"
        />

        <!-- Playlists Tab -->
        <PlaylistView 
          v-if="activeTab === 'playlists'"
          :playlists="playlists"
        />

        <!-- Job Progress Bar -->
        <div v-if="jobStatus && jobStatus.status === 'Running'" class="progress-panel">
          <div class="progress-header">
            <span class="progress-label">Processing...</span>
            <span class="progress-stats">
              {{ jobStatus.transcribed_tracks }}/{{ jobStatus.total_tracks }} transcribed
              · {{ jobStatus.analyzed_tracks }}/{{ jobStatus.total_tracks }} analyzed
            </span>
          </div>
          <div class="progress-bar-container">
            <div class="progress-bar" :style="{ width: progressPercent + '%' }"></div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { audioApi } from '../api/AudioApiClient'
import type { AudioTrack, Playlist, AudioJobSummary } from '../api/AudioApiClient'

import AudioSidebar from './AudioStudio/AudioSidebar.vue'
import AudioUpload from './AudioStudio/AudioUpload.vue'
import TranscriptionView from './AudioStudio/TranscriptionView.vue'
import PlaylistView from './AudioStudio/PlaylistView.vue'

const activeTab = ref('upload')
const jobs = ref<AudioJobSummary[]>([])
const selectedJob = ref<string | null>(null)
const jobStatus = ref<any>(null)
const tracks = ref<AudioTrack[]>([])
const playlists = ref<Playlist[]>([])
let pollInterval: ReturnType<typeof setInterval> | null = null

const tabTitle = computed(() => {
  if (activeTab.value === 'upload') return 'Upload & Process'
  if (activeTab.value === 'tracks') return 'Transcriptions'
  return 'AI Playlists'
})

const isPipelineRunning = computed(() => 
  jobStatus.value?.status === 'Running'
)

const progressPercent = computed(() => {
  if (!jobStatus.value || !jobStatus.value.total_tracks) return 0
  const total = jobStatus.value.total_tracks * 2  // transcription + analysis = 2 phases
  const done = (jobStatus.value.transcribed_tracks || 0) + (jobStatus.value.analyzed_tracks || 0)
  return Math.min(100, Math.round((done / total) * 100))
})

// ─── Data Fetching ────────────────────────────────────────────

async function loadJobs() {
  try {
    jobs.value = await audioApi.listJobs()
    // Auto-select the latest job if none selected
    if (!selectedJob.value && jobs.value.length > 0) {
      selectJob(jobs.value[0].name)
    }
  } catch (e) {
    console.error('Failed to load audio jobs:', e)
  }
}

async function selectJob(jobName: string) {
  selectedJob.value = jobName
  await loadJobData()
}

async function loadJobData() {
  if (!selectedJob.value) return

  try {
    jobStatus.value = await audioApi.getStatus(selectedJob.value)
    tracks.value = await audioApi.getTracks(selectedJob.value)
    playlists.value = await audioApi.getPlaylists(selectedJob.value)
  } catch (e) {
    console.error('Failed to load job data:', e)
  }
}

function onJobCreated(jobName: string) {
  selectedJob.value = jobName
  loadJobs()
  startPolling()
}

async function stopCurrentJob() {
  if (!selectedJob.value) return
  try {
    await audioApi.stopJob(selectedJob.value)
    await loadJobData()
  } catch (e) {
    console.error('Failed to stop job:', e)
  }
}

async function deleteCurrentJob() {
  if (!selectedJob.value) return
  if (!confirm('Delete this job and all its data?')) return
  try {
    await audioApi.deleteJob(selectedJob.value)
    selectedJob.value = null
    jobStatus.value = null
    tracks.value = []
    playlists.value = []
    await loadJobs()
  } catch (e) {
    console.error('Failed to delete job:', e)
  }
}

// ─── Polling ──────────────────────────────────────────────────

function startPolling() {
  stopPolling()
  pollInterval = setInterval(async () => {
    if (selectedJob.value) {
      await loadJobData()
      // Stop polling when job is done
      if (jobStatus.value && !['Running', 'Queued'].includes(jobStatus.value.status)) {
        stopPolling()
        loadJobs()  // Refresh sidebar
      }
    }
  }, 3000)
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

// Auto-start polling if current job is running
watch(jobStatus, (val) => {
  if (val && ['Running', 'Queued'].includes(val.status) && !pollInterval) {
    startPolling()
  }
})

onMounted(() => {
  loadJobs()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.top-bar {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.top-bar h2 {
  font-size: 18px;
  font-weight: 600;
  background: linear-gradient(135deg, var(--accent), var(--info));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.top-bar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.job-id-badge {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  background: var(--bg-input);
  padding: 3px 8px;
  border-radius: 4px;
}

.main-content {
  flex: 1;
  overflow-y: auto;
  height: 100%;
}

.progress-panel {
  margin-top: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.progress-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.progress-stats {
  font-size: 12px;
  color: var(--text-muted);
}

.progress-bar-container {
  height: 6px;
  background: var(--bg-input);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--success));
  border-radius: 3px;
  transition: width 0.5s ease;
}
</style>
