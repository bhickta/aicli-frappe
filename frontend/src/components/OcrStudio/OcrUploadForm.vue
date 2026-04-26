<script setup lang="ts">
/**
 * OcrUploadForm — Upload form for starting new OCR jobs.
 */
defineProps<{
  selectedFile: File | null
  selectedModel: string
  dpi: number
  maxWorkers: number
  availableModels: string[]
  loadingModels: boolean
  uploading: boolean
}>()

const emit = defineEmits<{
  'update:selectedModel': [value: string]
  'update:dpi': [value: number]
  'update:maxWorkers': [value: number]
  'file-select': [event: Event]
  'upload': []
  'refresh-models': []
}>()
</script>

<template>
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
          @change="emit('file-select', $event)"
          class="file-input"
        />
      </div>

      <div class="form-group">
        <label>Vision Model</label>
        <div class="model-select-row">
          <select
            :value="selectedModel"
            @input="emit('update:selectedModel', ($event.target as HTMLSelectElement).value)"
            class="form-select"
          >
            <option disabled value="">Select model…</option>
            <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
            <option v-if="availableModels.length === 0" disabled>No models found</option>
          </select>
          <button
            @click="emit('refresh-models')"
            class="btn-icon"
            :disabled="loadingModels"
            title="Refresh models"
          >
            {{ loadingModels ? '⏳' : '🔄' }}
          </button>
        </div>
      </div>

      <div class="form-group">
        <label>DPI (higher = better quality, slower)</label>
        <input
          type="number"
          :value="dpi"
          @input="emit('update:dpi', Number(($event.target as HTMLInputElement).value))"
          min="72" max="600" step="50"
          class="form-input"
        />
      </div>

      <div class="form-group">
        <label>Parallel Pages (Concurrency)</label>
        <input
          type="number"
          :value="maxWorkers"
          @input="emit('update:maxWorkers', Number(($event.target as HTMLInputElement).value))"
          min="1" max="32" step="1"
          class="form-input"
        />
      </div>

      <button
        class="btn btn-primary upload-btn"
        @click="emit('upload')"
        :disabled="!selectedFile || uploading"
      >
        {{ uploading ? '⏳ Uploading…' : '🚀 Upload & Start OCR' }}
      </button>
    </div>
  </div>
</template>
