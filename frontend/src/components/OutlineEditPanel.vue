<template>
  <div class="outline-edit-panel">
    <div class="panel-toolbar">
      <span class="toolbar-hint">📋 可编辑大纲文本（修改后点击保存）</span>
      <button class="action-btn ghost-btn small" @click="handleSave">💾 保存</button>
    </div>
    <textarea
      v-model="text"
      class="glass-input outline-textarea"
      placeholder="大纲数据加载中..."
    />
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  tree: { type: Array, default: () => [] },
})
const emit = defineEmits(['save'])

const text = ref('')

watch(() => props.tree, (val) => {
  const lines = []
  val.forEach(vol => {
    lines.push(`【${vol.volume_title || '未命名卷'}】`)
    vol.chapters?.forEach(ch => {
      lines.push(`  【${ch.chapter_title || '未命名章'}】`)
      ch.sections?.forEach(sec => {
        const status = sec.status === 'done' ? '✓' : '○'
        lines.push(`    ${status} 第${sec.section_order}节 | 标题：${sec.section_title || ''} | 概要：${sec.summary || ''}`)
      })
    })
  })
  text.value = lines.join('\n')
}, { immediate: true, deep: true })

function handleSave() {
  emit('save', text.value)
}
</script>

<style scoped>
.outline-edit-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--border);
}
.toolbar-hint {
  font-size: 12px;
  color: var(--text-muted);
}
.outline-textarea {
  flex: 1;
  resize: none;
  padding: var(--space-md);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.8;
  border-radius: 0;
  border: none;
}
</style>
