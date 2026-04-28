<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <h1>Audio Studio</h1>
      <div class="subtitle">MP3 → Text → Playlists</div>
    </div>

    <div class="sidebar-actions" style="margin-top: 16px;">
      <button class="btn" :class="activeTab === 'upload' ? 'btn-primary' : 'btn-ghost'" style="width: 100%; text-align: left; margin-bottom: 8px;" @click="$emit('update:activeTab', 'upload')">
        📤 Upload & Process
      </button>
      <button class="btn" :class="activeTab === 'tracks' ? 'btn-primary' : 'btn-ghost'" style="width: 100%; text-align: left; margin-bottom: 8px;" @click="$emit('update:activeTab', 'tracks')">
        📝 Transcriptions
      </button>
      <button class="btn" :class="activeTab === 'playlists' ? 'btn-primary' : 'btn-ghost'" style="width: 100%; text-align: left;" @click="$emit('update:activeTab', 'playlists')">
        🎧 Playlists
      </button>
    </div>

    <!-- Job List -->
    <div class="pdf-list" style="margin-top: 16px;" v-if="jobs.length > 0">
      <div class="sidebar-header" style="padding: 8px 12px; border-bottom: none;">
        <div class="subtitle" style="font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;">Recent Jobs</div>
      </div>
      <div 
        v-for="job in jobs" :key="job.name" 
        class="pdf-item" 
        :class="{ active: selectedJob === job.name }"
        @click="$emit('select-job', job.name)"
      >
        <span class="icon">🎵</span>
        <span style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          {{ job.total_tracks }} tracks
        </span>
        <span class="classification-badge" :class="jobBadgeClass(job.status)">{{ job.status }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
defineProps<{ 
  activeTab: string
  jobs: any[]
  selectedJob: string | null
}>()
defineEmits<{ 
  (e: 'update:activeTab', tab: string): void
  (e: 'select-job', name: string): void
}>()

function jobBadgeClass(status: string) {
  if (status === 'Completed') return 'badge-answer'
  if (status === 'Running') return 'badge-continuation'
  if (status === 'Failed') return 'badge-error'
  if (status === 'Paused') return 'badge-evaluation'
  return 'badge-pending'
}
</script>
