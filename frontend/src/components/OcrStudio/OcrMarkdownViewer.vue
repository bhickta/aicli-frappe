<script setup lang="ts">
/**
 * OcrMarkdownViewer — Markdown output viewer with download.
 */
defineProps<{
  markdown: string
}>()

const emit = defineEmits<{
  close: []
  download: []
}>()
</script>

<template>
  <div class="markdown-viewer">
    <div class="viewer-header">
      <h3>📝 Markdown Output</h3>
      <div class="viewer-actions">
        <button class="btn btn-secondary" @click="emit('download')">⬇️ Download .md</button>
        <button class="btn btn-ghost" @click="emit('close')">✕ Close</button>
      </div>
    </div>
    <pre class="markdown-content">{{ markdown }}</pre>
  </div>
</template>
