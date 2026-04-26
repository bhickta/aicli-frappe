<script setup lang="ts">
/**
 * OcrPageGrid — Visual grid of page status tiles.
 */
import type { OcrPage } from '../../types/ocr.types'

defineProps<{
  pages: OcrPage[]
  statusColor: (status: string) => string
}>()
</script>

<template>
  <div class="pages-grid">
    <div
      v-for="page in pages" :key="page.page_number"
      class="page-card" :class="page.status.toLowerCase()"
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
