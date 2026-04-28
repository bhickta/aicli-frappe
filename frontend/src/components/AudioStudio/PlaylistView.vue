<template>
  <div class="playlists-container">
    <div v-if="!playlists.length" class="empty-state">
      <div class="icon">🎧</div>
      <p>No playlists yet. Process audio files to generate AI playlists.</p>
    </div>

    <div v-else class="playlist-grid">
      <div v-for="(playlist, pIdx) in playlists" :key="pIdx" class="playlist-card">
        <!-- Playlist Header -->
        <div class="playlist-header">
          <div class="playlist-cover" :style="{ background: gradientForIndex(pIdx) }">
            <span class="playlist-cover-icon">🎵</span>
            <span class="playlist-track-count">{{ playlist.tracks?.length || 0 }}</span>
          </div>
          <div class="playlist-info">
            <h3 class="playlist-title">{{ playlist.playlist_name }}</h3>
            <p class="playlist-description">{{ playlist.description }}</p>
            <div class="playlist-meta">
              <span class="playlist-stat">{{ playlist.tracks?.length || 0 }} tracks</span>
              <span class="playlist-stat">{{ totalDuration(playlist) }}</span>
            </div>
          </div>
        </div>

        <!-- Track List -->
        <div class="playlist-tracks">
          <div 
            v-for="(track, tIdx) in (playlist.tracks || [])" 
            :key="track.name" 
            class="playlist-track-item"
          >
            <span class="track-index">{{ tIdx + 1 }}</span>
            <div class="track-details">
              <span class="track-name">{{ track.suggested_title || track.original_filename }}</span>
              <span class="track-sub-info">
                <span v-if="track.genre" class="mini-tag">{{ track.genre }}</span>
                <span v-if="track.mood" class="mini-tag mood">{{ track.mood }}</span>
              </span>
            </div>
            <span class="track-dur">{{ formatDuration(track.duration_seconds || 0) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Playlist } from '../../api/AudioApiClient'

defineProps<{ playlists: Playlist[] }>()

const gradients = [
  'linear-gradient(135deg, #6c5ce7, #a855f7)',
  'linear-gradient(135deg, #00cec9, #0984e3)',
  'linear-gradient(135deg, #e17055, #fdcb6e)',
  'linear-gradient(135deg, #00b894, #55efc4)',
  'linear-gradient(135deg, #fd79a8, #e84393)',
  'linear-gradient(135deg, #74b9ff, #0984e3)',
  'linear-gradient(135deg, #ffeaa7, #fdcb6e)',
  'linear-gradient(135deg, #dfe6e9, #636e72)',
]

function gradientForIndex(idx: number): string {
  return gradients[idx % gradients.length]
}

function formatDuration(seconds: number): string {
  const min = Math.floor(seconds / 60)
  const sec = Math.floor(seconds % 60)
  return `${min}:${sec.toString().padStart(2, '0')}`
}

function totalDuration(playlist: Playlist): string {
  const total = (playlist.tracks || []).reduce((sum, t) => sum + (t.duration_seconds || 0), 0)
  if (total < 60) return `${Math.round(total)}s`
  if (total < 3600) return `${Math.round(total / 60)}min`
  const h = Math.floor(total / 3600)
  const m = Math.round((total % 3600) / 60)
  return `${h}h ${m}m`
}
</script>

<style scoped>
.playlists-container {
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}

.playlist-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

.playlist-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: all 0.3s ease;
}

.playlist-card:hover {
  border-color: var(--border-light);
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}

.playlist-header {
  display: flex;
  gap: 16px;
  padding: 20px;
}

.playlist-cover {
  width: 80px;
  height: 80px;
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
}

.playlist-cover-icon {
  font-size: 28px;
  filter: brightness(1.2);
}

.playlist-track-count {
  font-size: 11px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
  margin-top: 2px;
}

.playlist-info {
  flex: 1;
  min-width: 0;
}

.playlist-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.playlist-description {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.playlist-meta {
  display: flex;
  gap: 12px;
}

.playlist-stat {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.playlist-tracks {
  padding: 0 16px 16px;
}

.playlist-track-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  border-radius: var(--radius);
  transition: background 0.2s;
}

.playlist-track-item:hover {
  background: var(--bg-card-hover);
}

.track-index {
  font-size: 12px;
  color: var(--text-muted);
  width: 20px;
  text-align: right;
  flex-shrink: 0;
  font-family: var(--font-mono);
}

.track-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.track-name {
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.track-sub-info {
  display: flex;
  gap: 6px;
}

.mini-tag {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--accent-dim);
  color: var(--accent);
}

.mini-tag.mood {
  background: var(--success-dim);
  color: var(--success);
}

.track-dur {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  flex-shrink: 0;
}
</style>
