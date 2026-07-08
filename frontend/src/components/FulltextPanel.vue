<template>
  <div class="fulltext-panel">
    <div v-if="loading" class="loading-state">
      <n-spin size="medium" />
      <p>加载中...</p>
    </div>
    <div v-else-if="content" class="fulltext-content">
      {{ content }}
    </div>
    <div v-else class="empty-content">
      <span class="empty-icon">📖</span>
      <p>暂无内容</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { NSpin } from 'naive-ui'
import { useNovelStore } from '../stores/novel.js'

const props = defineProps({
  novelId: String,
})

const store = useNovelStore()
const content = ref('')
const loading = ref(false)

watch(() => props.novelId, async (id) => {
  if (!id) return
  loading.value = true
  try {
    const data = await store.getFulltext()
    content.value = data.text || ''
  } catch (e) {
    content.value = '加载失败: ' + e.message
  } finally {
    loading.value = false
  }
}, { immediate: true })
</script>

<style scoped>
.fulltext-panel {
  padding: var(--space-lg);
  height: 100%;
  overflow-y: auto;
}
.fulltext-content {
  font-size: 14px;
  line-height: 2;
  white-space: pre-wrap;
  color: var(--text-primary);
}
.loading-state, .empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: var(--space-md);
}
.empty-icon { font-size: 48px; opacity: 0.5; }
</style>
