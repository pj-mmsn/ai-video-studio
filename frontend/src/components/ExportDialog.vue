<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog glass-card animate-in">
      <h3>📥 导出小说</h3>
      <div class="dialog-body">
        <label class="radio-label">
          <input type="radio" v-model="format" value="txt" />
          <span>纯文本 (.txt)</span>
        </label>
        <label class="radio-label">
          <input type="radio" v-model="format" value="html" />
          <span>网页 (.html)</span>
        </label>
      </div>
      <div class="dialog-footer">
        <button class="btn-ghost" @click="$emit('close')">取消</button>
        <a
          :href="exportUrl"
          class="btn-accent"
          download
          @click="$emit('close')"
        >
          下载
        </a>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useNovelStore } from '../stores/novel.js'

const props = defineProps({
  novelId: String,
})
defineEmits(['close'])

const store = useNovelStore()
const format = ref('txt')

const exportUrl = computed(() => store.getExportUrl(format.value))
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}
.dialog {
  width: 360px;
  padding: var(--space-xl);
}
.dialog h3 {
  font-size: 18px;
  margin-bottom: var(--space-lg);
}
.dialog-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-bottom: var(--space-xl);
}
.radio-label {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
}
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
}
.btn-ghost {
  padding: 8px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: all var(--transition-fast);
}
.btn-ghost:hover { background: var(--bg-hover); }
.btn-accent {
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--accent), #7c3aed);
  color: white;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: all var(--transition-fast);
}
.btn-accent:hover { box-shadow: 0 0 20px var(--accent-glow); }
</style>
