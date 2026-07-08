<template>
  <div class="execute-bar">
    <!-- 意见输入框 -->
    <input
      ref="fbInput"
      v-model="feedback"
      class="glass-input fb-input"
      :placeholder="placeholder"
      :disabled="isStreaming"
      @keydown.enter.exact="handleExecute"
    />

    <!-- 执行按钮 -->
    <button
      class="execute-btn accent-btn pulse-glow"
      :disabled="isStreaming || !canExecute"
      @click="handleExecute"
    >
      {{ isStreaming ? '⏳' : '⚡' }} {{ btnLabel }}
    </button>

    <!-- 编辑正文 -->
    <button
      :class="['icon-btn', { active: isEditMode }]"
      :disabled="isStreaming"
      @click="$emit('toggle-edit')"
      :title="isEditMode ? '保存修改' : '编辑正文'"
    >
      {{ isEditMode ? '💾' : '✏️' }}
    </button>

    <!-- 搜索 -->
    <button
      class="icon-btn"
      @click="$emit('search')"
      title="搜索 (Ctrl+F)"
    >
      🔍
    </button>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  mode: String,
  isStreaming: Boolean,
  isEditMode: Boolean,
  hasSelection: Boolean,
})

const emit = defineEmits(['execute', 'toggle-edit', 'search'])

const feedback = ref('')
const fbInput = ref(null)

const canExecute = computed(() => {
  if (props.mode === 'write') return props.hasSelection
  return true
})

const placeholder = computed(() => {
  if (props.mode === 'write') return '修改意见（可选，直接回车执行写作）...'
  return '按 Ctrl+Enter 或点击执行按钮...'
})

const btnLabel = computed(() => {
  if (props.mode === 'write') return props.isEditMode ? '修订' : '写作'
  return '执行'
})

function handleExecute() {
  emit('execute', feedback.value)
}

// Ctrl+Enter 快捷键
function handleKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    handleExecute()
  }
}

watch(() => props.isStreaming, (val) => {
  if (!val) {
    // 完成后聚焦输入框
    setTimeout(() => fbInput.value?.focus(), 100)
  }
})
</script>

<style scoped>
.execute-bar {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--border);
}

.fb-input {
  flex: 1;
  padding: 8px var(--space-md);
  font-size: 13px;
}

.execute-btn {
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  background: linear-gradient(135deg, var(--accent), #7c3aed);
  color: white;
  transition: all var(--transition-fast);
}
.execute-btn:hover:not(:disabled) {
  box-shadow: 0 0 20px var(--accent-glow);
}
.execute-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon-btn {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.icon-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.icon-btn.active {
  background: var(--accent-glow);
  border-color: var(--accent);
  color: var(--accent);
}
.icon-btn:disabled {
  opacity: 0.4;
}
</style>
