<script setup lang="ts">
/**
 * OcrErrorLog — Displays failed page errors.
 */
import type { OcrPage } from '../../types/ocr.types'

defineProps<{
  pages: OcrPage[]
}>()

</script>

<template>
  <div class="error-log">
    <h4>⚠ Failed Page Logs</h4>
    <ul>
      <li v-for="page in pages.filter(p => p.status === 'Failed' && p.error)" :key="page.page_number">
        <strong>Page {{ page.page_number }}:</strong> <span>{{ page.error }}</span>
      </li>
    </ul>
  </div>
</template>
