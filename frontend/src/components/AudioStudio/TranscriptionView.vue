<template>
  <div class="tracks-container">
    <div v-if="!tracks.length" class="empty-state">
      <div class="icon">📝</div>
      <p>No tracks yet. Upload audio files to get started.</p>
    </div>

    <div v-else>
      <!-- Progress summary -->
      <div class="track-summary">
        <div class="status-chip pdfs">{{ tracks.length }} tracks</div>
        <div class="status-chip classified">{{ tracks.filter(t => t.status === 'Completed').length }} analyzed</div>
        <div class="status-chip pages">{{ tracks.filter(t => t.status === 'Transcribed' || t.status === 'Analyzing').length }} in progress</div>
        <div v-if="tracks.some(t => t.status === 'Failed')" class="status-chip errors">
          {{ tracks.filter(t => t.status === 'Failed').length }} failed
        </div>
      </div>

      <!-- Track list -->
      <div class="track-list">
        <div 
          v-for="track in tracks" :key="track.name" 
          class="track-card"
          :class="{ 'track-selected': selectedTrack === track.name }"
          @click="selectedTrack = selectedTrack === track.name ? null : track.name"
        >
          <div class="track-card-header">
            <div class="track-info">
              <span class="track-status-dot" :class="statusDotClass(track.status)"></span>
              <span class="track-title">{{ track.suggested_title || track.original_filename }}</span>
            </div>
            <div class="track-meta">
              <span v-if="track.duration_seconds" class="track-duration">
                {{ formatDuration(track.duration_seconds) }}
              </span>
              <span class="classification-badge" :class="statusBadgeClass(track.status)">
                {{ track.status }}
              </span>
            </div>
          </div>

          <!-- Tags row -->
          <div class="track-tags" v-if="track.genre || track.mood || track.content_type">
            <span v-if="track.genre" class="tag tag-genre">{{ track.genre }}</span>
            <span v-if="track.mood" class="tag tag-mood">{{ track.mood }}</span>
            <span v-if="track.content_type" class="tag tag-type">{{ track.content_type }}</span>
            <span v-if="track.language" class="tag tag-lang">{{ track.language }}</span>
          </div>

          <!-- Topics -->
          <div class="track-topics" v-if="track.topics && track.topics.length">
            <span v-for="topic in track.topics.slice(0, 4)" :key="topic" class="topic-chip">
              {{ topic }}
            </span>
          </div>

          <!-- Expanded: transcript + summary -->
          <div class="track-expanded" v-if="selectedTrack === track.name">
            <div v-if="track.summary" class="track-summary-text">
              <strong>Summary:</strong> {{ track.summary }}
            </div>

            <div v-if="track.transcript" class="track-transcript">
              <div class="transcript-header">
                <strong>Transcript</strong>
                <button class="btn btn-ghost btn-sm" @click.stop="copyTranscript(track.transcript)">
                  📋 Copy
                </button>
              </div>
              <pre class="transcript-body">{{ truncateTranscript(track.transcript) }}</pre>
            </div>

            <div v-if="track.error" class="track-error">
              <strong>Error:</strong> {{ track.error }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { AudioTrack } from '../../api/AudioApiClient'

defineProps<{ tracks: AudioTrack[] }>()

const selectedTrack = ref<string | null>(null)

function formatDuration(seconds: number): string {
  const min = Math.floor(seconds / 60)
  const sec = Math.floor(seconds % 60)
  return `${min}:${sec.toString().padStart(2, '0')}`
}

function statusDotClass(status: string) {
  if (status === 'Completed') return 'dot-completed'
  if (status === 'Transcribing' || status === 'Analyzing') return 'dot-processing'
  if (status === 'Failed') return 'dot-failed'
  if (status === 'Transcribed') return 'dot-partial'
  return 'dot-pending'
}

function statusBadgeClass(status: string) {
  if (status === 'Completed') return 'badge-answer'
  if (status === 'Transcribing' || status === 'Analyzing') return 'badge-continuation'
  if (status === 'Failed') return 'badge-error'
  if (status === 'Transcribed') return 'badge-evaluation'
  return 'badge-pending'
}

function truncateTranscript(text: string): string {
  return text.length > 2000 ? text.slice(0, 2000) + '\n\n... [truncated]' : text
}

function copyTranscript(text: string) {
  navigator.clipboard.writeText(text)
}
</script>

<style scoped>
.tracks-container {
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}

.track-summary {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.track-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.track-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.track-card:hover {
  border-color: var(--border-light);
  background: var(--bg-card-hover);
}

.track-selected {
  border-color: var(--accent) !important;
  background: var(--accent-dim) !important;
}

.track-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.track-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.track-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-completed { background: var(--success); box-shadow: 0 0 6px var(--success); }
.dot-processing { background: var(--warning); animation: pulse 1.5s infinite; }
.dot-failed { background: var(--danger); }
.dot-partial { background: var(--info); }
.dot-pending { background: var(--text-muted); opacity: 0.4; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.track-title {
  font-weight: 500;
  font-size: 14px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.track-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.track-duration {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.track-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.tag {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 8px;
  border-radius: 4px;
}

.tag-genre { background: var(--accent-dim); color: var(--accent); }
.tag-mood { background: var(--success-dim); color: var(--success); }
.tag-type { background: var(--info-dim); color: var(--info); }
.tag-lang { background: var(--warning-dim); color: var(--warning); }

.track-topics {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.topic-chip {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 12px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

.track-expanded {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.track-summary-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 12px;
}

.track-transcript {
  margin-top: 8px;
}

.transcript-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.transcript-body {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  font-size: 12px;
  color: var(--text-secondary);
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  line-height: 1.6;
}

.track-error {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--danger-dim);
  color: var(--danger);
  border-radius: var(--radius);
  font-size: 12px;
}
</style>
