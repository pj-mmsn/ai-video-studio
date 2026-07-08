<template>
  <div class="search-bar glass-panel">
    <input
      ref="searchInput"
      v-model="query"
      class="glass-input search-input"
      placeholder="搜索正文..."
      @input="handleSearch"
    />
    <span class="search-count" v-if="query">{{ matchCount }} 处匹配</span>
    <button class="close-btn" @click="$emit('close')">✕</button>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
})
const emit = defineEmits(['close', 'search'])

const query = ref('')
const matchCount = ref(0)
const searchInput = ref(null)

onMounted(() => {
  nextTick(() => searchInput.value?.focus())
})

function handleSearch() {
  if (!query.value || !props.content) {
    matchCount.value = 0
    return
  }
  const escaped = query.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const matches = props.content.match(new RegExp(escaped, 'gi'))
  matchCount.value = matches ? matches.length : 0
  emit('search', query.value)
}
</script>

<style scoped>
.search-bar {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--border);
}
.search-input {
  flex: 1;
  padding: 6px var(--space-sm);
  font-size: 13px;
}
.search-count {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}
.close-btn {
  padding: 4px 8px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 14px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}
.close-btn:hover {
  background: var(--bg-hover);
  color: var(--error);
}
</style>
