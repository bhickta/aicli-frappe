<template>
  <div class="config-card">
    <h3 style="margin-bottom: 8px;">Upload & Transcribe Audio</h3>
    <p class="description">
      Upload MP3/audio files to transcribe with Whisper, analyze content with AI, and automatically group into playlists.
    </p>

    <!-- Drop Zone -->
    <div 
      class="audio-dropzone" 
      :class="{ 'dropzone-active': isDragging, 'dropzone-has-files': selectedFiles.length > 0 }"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="handleDrop"
      @click="triggerFileInput"
    >
      <div v-if="selectedFiles.length === 0" class="dropzone-empty">
        <span class="dropzone-icon">🎵</span>
        <p>Drag & drop audio files here</p>
        <p class="dropzone-hint">or click to browse — MP3, WAV, M4A, OGG, FLAC</p>
      </div>
      <div v-else class="dropzone-files">
        <div class="file-count-badge">{{ selectedFiles.length }} files selected</div>
        <div class="file-list-preview">
          <div v-for="(f, i) in selectedFiles.slice(0, 8)" :key="i" class="file-chip">
            <span class="file-chip-icon">🎵</span>
            <span class="file-chip-name">{{ f.name }}</span>
            <span class="file-chip-size">{{ formatSize(f.size) }}</span>
            <button class="file-chip-remove" @click.stop="removeFile(i)">×</button>
          </div>
          <div v-if="selectedFiles.length > 8" class="file-chip file-chip-more">
            +{{ selectedFiles.length - 8 }} more
          </div>
        </div>
      </div>
      <input ref="fileInput" type="file" multiple accept=".mp3,.wav,.m4a,.ogg,.flac,.aac,.wma,.opus" @change="handleFileSelect" style="display: none;" />
    </div>

    <!-- Config -->
    <div class="config-grid" style="margin-top: 20px;">
      <div class="form-group">
        <label>Whisper Model</label>
        <select v-model="whisperModel" class="form-select">
          <option value="tiny">tiny (fastest)</option>
          <option value="base">base (balanced)</option>
          <option value="small">small</option>
          <option value="medium">medium</option>
          <option value="large-v3">large-v3 (best)</option>
        </select>
      </div>

      <div class="form-group">
        <label>LLM Model (Analysis)</label>
        <div class="select-wrapper">
          <select v-model="llmModel" class="form-select">
            <option disabled value="">Select a model...</option>
            <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
            <option v-if="availableModels.length === 0" disabled>No models found</option>
          </select>
          <button @click="refreshModels" class="btn-icon" title="Refresh Models" :disabled="loadingModels">
            <span v-if="!loadingModels">🔄</span>
            <span v-else class="spin">⏳</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div style="margin-top: 24px; display: flex; gap: 12px; align-items: center;">
      <button 
        class="btn btn-primary" 
        style="font-size: 14px; padding: 12px 24px;" 
        @click="handleUploadAndStart"
        :disabled="uploading || selectedFiles.length === 0 || pipelineRunning"
      >
        <span v-if="uploading" class="spinner" style="width: 14px; height: 14px;"></span>
        {{ uploading ? 'Uploading...' : pipelineRunning ? 'Processing...' : '▶ Upload & Process' }}
      </button>
      <button 
        v-if="pipelineRunning" 
        class="btn btn-danger" 
        @click="$emit('stop')"
      >
        ⏹ Stop
      </button>
    </div>

    <!-- Upload Progress -->
    <div v-if="uploadStatus" class="upload-status" :class="uploadStatus.type">
      {{ uploadStatus.message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { audioApi } from '../../api/AudioApiClient'
import { settingsApi } from '../../api/SettingsApiClient'

const props = defineProps<{ pipelineRunning: boolean }>()
const emit = defineEmits<{
  (e: 'job-created', jobName: string): void
  (e: 'stop'): void
}>()

const selectedFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const uploading = ref(false)
const whisperModel = ref('base')
const llmModel = ref('')
const availableModels = ref<string[]>([])
const loadingModels = ref(false)
const uploadStatus = ref<{ message: string; type: string } | null>(null)

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) {
    selectedFiles.value = [...selectedFiles.value, ...Array.from(input.files)]
  }
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer?.files) {
    const audioFiles = Array.from(e.dataTransfer.files).filter(f => 
      /\.(mp3|wav|m4a|ogg|flac|aac|wma|opus)$/i.test(f.name)
    )
    selectedFiles.value = [...selectedFiles.value, ...audioFiles]
  }
}

function removeFile(index: number) {
  selectedFiles.value.splice(index, 1)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1048576).toFixed(1) + 'MB'
}

async function refreshModels() {
  loadingModels.value = true
  try {
    const { models } = await settingsApi.fetchModels()
    availableModels.value = models
    if (models.length > 0 && !llmModel.value) {
      llmModel.value = models[0]
    }
  } catch (e) {
    console.error('Failed to fetch models:', e)
  } finally {
    loadingModels.value = false
  }
}

async function handleUploadAndStart() {
  if (selectedFiles.value.length === 0) return

  uploading.value = true
  uploadStatus.value = { message: 'Uploading files...', type: 'info' }

  try {
    // Upload and create job
    const result = await audioApi.uploadFiles(
      selectedFiles.value, whisperModel.value, llmModel.value
    )
    uploadStatus.value = { 
      message: `Uploaded ${result.tracks} tracks. Starting pipeline...`, 
      type: 'success' 
    }

    // Start the pipeline
    await audioApi.startPipeline(result.job_name)
    uploadStatus.value = { 
      message: `Pipeline started for ${result.tracks} tracks!`, 
      type: 'success' 
    }

    emit('job-created', result.job_name)
    selectedFiles.value = []

  } catch (err: any) {
    uploadStatus.value = { message: 'Upload failed: ' + err.message, type: 'error' }
  } finally {
    uploading.value = false
  }
}

onMounted(refreshModels)
</script>

<style scoped>
.audio-dropzone {
  border: 2px dashed var(--border-light);
  border-radius: var(--radius-lg);
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: var(--bg-input);
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.audio-dropzone:hover, .dropzone-active {
  border-color: var(--accent);
  background: var(--accent-dim);
}

.dropzone-has-files {
  border-style: solid;
  border-color: var(--success);
  background: var(--success-dim);
}

.dropzone-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.dropzone-icon {
  font-size: 40px;
  opacity: 0.4;
}

.dropzone-empty p {
  color: var(--text-secondary);
  font-size: 14px;
  margin: 0;
}

.dropzone-hint {
  font-size: 12px !important;
  color: var(--text-muted) !important;
}

.dropzone-files {
  width: 100%;
}

.file-count-badge {
  font-size: 13px;
  font-weight: 600;
  color: var(--success);
  margin-bottom: 12px;
}

.file-list-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 4px 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.file-chip-icon { font-size: 14px; }

.file-chip-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-chip-size {
  color: var(--text-muted);
  font-size: 10px;
}

.file-chip-remove {
  background: none;
  border: none;
  color: var(--danger);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.file-chip-remove:hover { opacity: 1; }

.file-chip-more {
  color: var(--text-muted);
  border-style: dashed;
}

.select-wrapper {
  display: flex;
  gap: 8px;
  align-items: center;
}

.form-select {
  flex: 1;
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: var(--radius);
  font-family: inherit;
  font-size: 13px;
}

.form-select:focus { border-color: var(--accent); outline: none; }

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.btn-icon:hover { opacity: 1; }

.spin {
  display: inline-block;
  animation: spin 1s linear infinite;
}

.upload-status {
  margin-top: 16px;
  padding: 10px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
}

.upload-status.info { background: var(--info-dim); color: var(--info); }
.upload-status.success { background: var(--success-dim); color: var(--success); }
.upload-status.error { background: var(--danger-dim); color: var(--danger); }
</style>
