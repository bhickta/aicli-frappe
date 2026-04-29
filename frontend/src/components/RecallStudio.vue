<template>
  <div class="studio-container recall-studio">
    <div class="studio-header">
      <div class="header-content">
        <h2>UPSC Recall Engine</h2>
        <p>Generate high-entropy broad recall triggers from your study notes. Strict UPSC examiner logic applied.</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="showHistory = !showHistory">
          {{ showHistory ? 'View Workspace' : 'View History' }}
        </button>
      </div>
    </div>

    <div class="studio-content" v-if="!showHistory">
      <div class="input-section">
        <div class="card glass">
          <div class="card-header">
            <h3>Input Study Notes</h3>
            <span class="badge">Strict Logic</span>
          </div>
          <textarea 
            v-model="notes" 
            placeholder="Paste your UPSC notes here (e.g. Geography, History, Polity concepts)..."
            class="notes-textarea"
          ></textarea>
          <div class="card-footer">
            <div class="stats">
              <span>{{ notes.length }} characters</span>
            </div>
            <button 
              class="btn btn-primary generate-btn" 
              :disabled="loading || !notes.trim()"
              @click="generateTriggers"
            >
              <span v-if="!loading">🚀 Generate Triggers</span>
              <span v-else class="loading-spinner">⏳ Processing...</span>
            </button>
          </div>
        </div>
      </div>

      <div class="output-section" v-if="triggers || loading">
        <div class="card results-card" :class="{ 'loading-state': loading }">
          <div class="card-header">
            <h3>Recall Triggers</h3>
            <button v-if="triggers" class="btn btn-icon" @click="copyTriggers" title="Copy to Clipboard">
              📋
            </button>
          </div>
          <div class="triggers-display" v-if="triggers">
            <div class="trigger-item" v-for="(trigger, idx) in formattedTriggers" :key="idx">
              <span class="trigger-num">{{ idx + 1 }}</span>
              <p>{{ trigger }}</p>
            </div>
          </div>
          <div class="loading-placeholder" v-else>
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="history-view" v-else>
      <div class="history-grid">
        <div v-for="item in history" :key="item.name" class="history-card glass">
          <div class="history-meta">
            <span class="history-date">{{ formatDate(item.timestamp) }}</span>
            <span class="history-model">{{ item.model }}</span>
          </div>
          <div class="history-triggers">
            <p v-for="(t, i) in formatTriggersList(item.triggers)" :key="i">
              {{ t }}
            </p>
          </div>
          <div class="history-actions">
            <button class="btn btn-small" @click="loadFromHistory(item)">Restore Notes</button>
            <button class="btn btn-small btn-icon" @click="copyText(item.triggers)">📋</button>
          </div>
        </div>
      </div>
      <div v-if="history.length === 0" class="empty-history">
        <p>No history found. Generate some triggers first!</p>
      </div>
    </div>

    <!-- Toast Notification -->
    <Transition name="fade">
      <div v-if="toast" class="toast" :class="toast.type">
        {{ toast.message }}
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { recallApi, type RecallHistoryItem } from '../api/RecallApiClient'

const notes = ref('')
const triggers = ref('')
const loading = ref(false)
const showHistory = ref(false)
const history = ref<RecallHistoryItem[]>([])
const toast = ref<{ message: string, type: 'success' | 'error' } | null>(null)

const formattedTriggers = computed(() => {
  if (!triggers.value) return []
  return triggers.value.split('\n').filter(line => line.trim().startsWith('*')).map(line => line.replace(/^\*\s*/, '').trim())
})

function formatTriggersList(triggerStr: string) {
  return triggerStr.split('\n').filter(line => line.trim().startsWith('*')).map(line => line.replace(/^\*\s*/, '').trim())
}

async function generateTriggers() {
  loading.value = true
  try {
    const res = await recallApi.generateTriggers(notes.value)
    triggers.value = res.triggers
    showToast('Triggers generated successfully!', 'success')
    await fetchHistory()
  } catch (err: any) {
    showToast(err.message || 'Generation failed', 'error')
  } finally {
    loading.value = false
  }
}

async function fetchHistory() {
  try {
    history.value = await recallApi.getHistory()
  } catch (err) {
    console.error('Failed to fetch history', err)
  }
}

function copyTriggers() {
  copyText(triggers.value)
}

function copyText(text: string) {
  navigator.clipboard.writeText(text)
  showToast('Copied to clipboard!', 'success')
}

function showToast(message: string, type: 'success' | 'error') {
  toast.value = { message, type }
  setTimeout(() => toast.value = null, 3000)
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString()
}

function loadFromHistory(item: RecallHistoryItem) {
  notes.value = item.notes
  triggers.value = item.triggers
  showHistory.value = false
}

onMounted(fetchHistory)
</script>

<style scoped>
.studio-container {
  padding: 32px 48px;
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: radial-gradient(circle at top right, rgba(144, 150, 255, 0.05), transparent 40%),
              radial-gradient(circle at bottom left, rgba(144, 150, 255, 0.03), transparent 40%);
}

.studio-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.header-content h2 {
  font-size: 32px;
  font-weight: 800;
  background: linear-gradient(135deg, #fff 0%, #9096ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 8px;
}

.header-content p {
  color: var(--text-secondary);
  font-size: 16px;
}

.studio-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
  flex-grow: 1;
}

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: all 0.3s ease;
}

.card.glass {
  background: rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.card-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.badge {
  background: rgba(144, 150, 255, 0.2);
  color: #9096ff;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.notes-textarea {
  flex-grow: 1;
  padding: 24px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.6;
  resize: none;
  min-height: 400px;
  outline: none;
}

.card-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stats {
  color: var(--text-secondary);
  font-size: 13px;
}

.generate-btn {
  padding: 12px 24px;
  font-weight: 600;
  border-radius: 10px;
}

.results-card {
  height: fit-content;
  min-height: 300px;
}

.triggers-display {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.trigger-item {
  display: flex;
  gap: 16px;
  background: rgba(255, 255, 255, 0.02);
  padding: 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  animation: slideUp 0.4s ease forwards;
}

.trigger-num {
  font-weight: 800;
  color: var(--accent);
  font-size: 18px;
}

.trigger-item p {
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.5;
}

.loading-placeholder {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.skeleton-line {
  height: 20px;
  background: linear-gradient(90deg, rgba(255,255,255,0.05) 25%, rgba(255,255,255,0.1) 50%, rgba(255,255,255,0.05) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 24px;
}

.history-card {
  padding: 24px;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.history-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
}

.history-triggers {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-triggers p {
  font-size: 14px;
  color: var(--text-primary);
  border-left: 2px solid var(--accent);
  padding-left: 10px;
}

.history-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}

.toast {
  position: fixed;
  bottom: 40px;
  right: 40px;
  padding: 16px 24px;
  border-radius: 12px;
  color: white;
  font-weight: 600;
  box-shadow: 0 10px 30px rgba(0,0,0,0.3);
  z-index: 1000;
}

.toast.success { background: #10b981; border: 1px solid #059669; }
.toast.error { background: #ef4444; border: 1px solid #dc2626; }

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.btn-small {
  padding: 6px 12px;
  font-size: 12px;
}
</style>
