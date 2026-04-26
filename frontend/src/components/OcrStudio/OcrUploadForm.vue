<script setup lang="ts">
/**
 * OcrUploadForm — Upload form for starting new OCR jobs from ZIP files.
 */
defineProps<{
  selectedModel: string
  maxWorkers: number
  availableModels: string[]
  loadingModels: boolean
  uploading: boolean
}>()

const emit = defineEmits<{
  'update:selectedModel': [value: string]
  'update:maxWorkers': [value: number]
  'native-upload': []
  'refresh-models': []
}>()
</script>

<template>
  <div class="upload-section">
    <h3>📄 ZIP Images → Markdown OCR</h3>
    <p class="subtitle">Upload a ZIP file containing images (JPG/PNG) and extract text using a local LLM vision model.</p>

    <div class="upload-form">
      <div class="form-group">
        <label>ZIP File</label>
        <button
          class="btn btn-secondary native-upload-btn"
          @click="emit('native-upload')"
          :disabled="uploading"
        >
          {{ uploading ? '⏳ Processing…' : '📁 Choose ZIP (Native Upload)' }}
        </button>
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
        <label>Parallel Pages (Concurrency)</label>
        <input
          type="number"
          :value="maxWorkers"
          @input="emit('update:maxWorkers', Number(($event.target as HTMLInputElement).value))"
          min="1" max="32" step="1"
          class="form-input"
        />
      </div>

      <div class="info-note" v-if="!uploading">
        💡 Use Frappe's native uploader for better handling of large files (>500MB).
      </div>
    </div>
  </div>
</template>
