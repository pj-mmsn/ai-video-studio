<template>
  <div class="content-panel" ref="panelRef">
    <!-- 流式打字指示器 -->
    <div v-if="isStreaming && !content" class="streaming-placeholder">
      <span class="typing-dot" />
      <span class="typing-dot delay-1" />
      <span class="typing-dot delay-2" />
      <p>AI 正在创作...</p>
    </div>

    <!-- 内容展示 -->
    <div
      v-if="content || isStreaming"
      :class="['content-body', { 'typing-cursor': isStreaming }]"
      :contenteditable="isEditMode && !isStreaming"
      @input="handleInput"
      ref="contentRef"
    >
      <!-- 使用 v-html 渲染已格式化文本，但流式时不渲染 HTML -->
      <div v-if="!isStreaming" v-html="renderedContent" />
      <div v-else class="streaming-text">{{ content }}</div>
    </div>

    <!-- 空状态 -->
    <div v-if="!content && !isStreaming" class="empty-content">
      <span class="empty-icon">📝</span>
      <p>选择左侧大纲中的一节，然后点击"执行"开始写作</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
  isStreaming: Boolean,
  isEditMode: Boolean,
})

const emit = defineEmits(['update:content'])

const contentRef = ref(null)
const panelRef = ref(null)

const renderedContent = computed(() => {
  if (!props.content) return ''
  // 简单 Markdown 渲染：段落换行
  return props.content
    .split('\n')
    .map(line => line ? `<p>${line}</p>` : '<br/>')
    .join('')
})

function handleInput(e) {
  emit('update:content', e.target.innerText)
}

// 自动滚动到底部
watch(() => props.content, async () => {
  await nextTick()
  if (panelRef.value) {
    panelRef.value.scrollTop = panelRef.value.scrollHeight
  }
})
</script>

<style scoped>
.content-panel {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-lg);
}

.streaming-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  gap: var(--space-md);
  color: var(--accent);
}

.typing-dot {
  width: 8px;
  height: 8px;
  background: var(--accent);
  border-radius: 50%;
  animation: bounce-dot 1.4s infinite ease-in-out both;
}
.typing-dot.delay-1 { animation-delay: -0.32s; }
.typing-dot.delay-2 { animation-delay: -0.16s; }

@keyframes bounce-dot {
  0%, 80%, 100% { transform: scale(0); opacity: 0.3; }
  40% { transform: scale(1); opacity: 1; }
}

.content-body {
  font-size: 15px;
  line-height: 1.9;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.content-body[contenteditable="true"] {
  outline: 2px dashed var(--accent);
  border-radius: var(--radius-sm);
  padding: var(--space-sm);
}

.streaming-text {
  color: var(--text-primary);
}

.empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: var(--space-md);
}
.empty-icon {
  font-size: 48px;
  opacity: 0.5;
}
</style>
