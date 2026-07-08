<template>
  <aside class="sidebar glass-panel">
    <!-- Logo + 项目名 -->
    <div class="sidebar-header">
      <h2 class="sidebar-logo neon-text">✍️ AI 小说家</h2>
      <p class="sidebar-project">{{ novel?.title || '未打开项目' }}</p>
    </div>

    <!-- 模式按钮 -->
    <div class="mode-buttons">
      <button
        v-for="m in modes"
        :key="m.key"
        :class="['mode-btn', { active: mode === m.key }]"
        @click="$emit('mode-change', m.key)"
      >
        <span class="mode-icon">{{ m.icon }}</span>
        <span class="mode-label">{{ m.label }}</span>
      </button>
    </div>

    <div class="sidebar-divider" />

    <!-- 模式面板 -->
    <div class="mode-panel">
      <!-- 构思面板 -->
      <div v-if="mode === 'idea'" class="animate-in">
        <label class="panel-label">💡 故事想法</label>
        <textarea
          ref="ideaInput"
          class="glass-input idea-input"
          placeholder="输入你的故事想法..."
          rows="4"
        ></textarea>
        <button
          class="action-btn accent-btn"
          :disabled="isStreaming"
          @click="$emit('generate-idea', $refs.ideaInput?.value || '')"
        >
          {{ isStreaming ? '⏳ 生成中...' : '✨ 生成构思' }}
        </button>
      </div>

      <!-- 大纲面板 -->
      <div v-else-if="mode === 'outline'" class="animate-in">
        <label class="panel-label">📋 大纲设置</label>
        <div class="outline-settings">
          <div class="setting-row">
            <span>卷数</span>
            <input ref="volInput" class="glass-input num-input" type="number" value="3" min="1" max="10" />
          </div>
          <div class="setting-row">
            <span>每卷章数</span>
            <input ref="chInput" class="glass-input num-input" type="number" value="4" min="1" max="20" />
          </div>
        </div>
        <button
          class="action-btn accent-btn"
          :disabled="isStreaming"
          @click="$emit('generate-outline',
            parseInt($refs.volInput?.value || 3),
            parseInt($refs.chInput?.value || 4)
          )"
        >
          {{ isStreaming ? '⏳ 生成中...' : '📋 生成大纲' }}
        </button>
        <button class="action-btn ghost-btn" @click="showBatch = !showBatch">
          🔄 批量替换
        </button>
        <div v-if="showBatch" class="batch-area animate-in">
          <input ref="batchFind" class="glass-input" placeholder="查找..." />
          <input ref="batchReplace" class="glass-input" placeholder="替换为..." />
          <button class="action-btn ghost-btn small" @click="$emit('batch-replace',
            $refs.batchFind?.value || '',
            $refs.batchReplace?.value || ''
          ); showBatch = false">
            执行替换
          </button>
        </div>
      </div>

      <!-- 写作面板 -->
      <div v-else-if="mode === 'write'" class="animate-in">
        <label class="panel-label">✍️ 写作进度</label>
        <div class="progress-bar-container">
          <div class="progress-bar">
            <div class="progress-fill shimmer" :style="{ width: (progress?.pct || 0) + '%' }" />
          </div>
          <p class="progress-text">
            {{ progress?.done || 0 }} / {{ progress?.total || 0 }} 节 ·
            {{ (progress?.words || 0).toLocaleString() }} 字
          </p>
        </div>
        <div v-if="isStreaming" class="streaming-indicator breathe">
          ✨ AI 正在创作...
        </div>
      </div>

      <!-- 审稿面板 -->
      <div v-else-if="mode === 'review'" class="animate-in">
        <label class="panel-label">🔍 全文审稿</label>
        <p class="panel-hint">AI 将对照大纲逐节审核正文，检查一致性、连贯性和节奏。</p>
        <button
          class="action-btn accent-btn"
          :disabled="isStreaming"
          @click="$emit('start-review')"
        >
          {{ isStreaming ? '⏳ 审稿中...' : '🔍 开始审稿' }}
        </button>
      </div>
    </div>

    <div class="sidebar-spacer" />

    <!-- 底部工具栏 -->
    <div class="sidebar-footer">
      <button class="action-btn ghost-btn small" @click="$emit('export')">
        📥 导出小说
      </button>
      <select class="glass-input model-select" :value="modelName" @change="$emit('model-change', $event.target.value)">
        <option value="deepseek-v4-pro">deepseek-v4-pro</option>
        <option value="deepseek-v4-flash">deepseek-v4-flash</option>
      </select>
    </div>
  </aside>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  mode: String,
  novel: Object,
  idea: Object,
  progress: Object,
  isStreaming: Boolean,
  modelName: String,
})

defineEmits([
  'mode-change', 'generate-idea', 'generate-outline',
  'batch-replace', 'start-review', 'export', 'model-change',
])

const showBatch = ref(false)

const modes = [
  { key: 'idea', icon: '💡', label: '构思' },
  { key: 'outline', icon: '📋', label: '大纲' },
  { key: 'write', icon: '✍️', label: '写作' },
  { key: 'review', icon: '🔍', label: '审稿' },
]
</script>

<style scoped>
.sidebar {
  width: 240px;
  display: flex;
  flex-direction: column;
  padding: var(--space-lg) var(--space-md);
  overflow-y: auto;
}

.sidebar-header {
  margin-bottom: var(--space-lg);
}
.sidebar-logo {
  font-size: 18px;
  font-weight: 800;
  margin-bottom: 4px;
}
.sidebar-project {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mode-buttons {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mode-btn {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 10px 14px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
}
.mode-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.mode-btn.active {
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.2), rgba(34, 211, 238, 0.1));
  color: var(--accent);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px var(--accent-glow);
}

.mode-icon { font-size: 16px; }
.mode-label { flex: 1; }

.sidebar-divider {
  height: 1px;
  background: var(--border);
  margin: var(--space-md) 0;
}

.mode-panel {
  flex: 1;
  overflow-y: auto;
}

.panel-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: var(--space-sm);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.panel-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: var(--space-md);
  line-height: 1.5;
}

.idea-input {
  width: 100%;
  resize: vertical;
  min-height: 80px;
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-sm);
  font-family: var(--font-sans);
  font-size: 13px;
}

.outline-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-secondary);
}
.num-input {
  width: 60px;
  padding: 4px 8px;
  text-align: center;
}

.batch-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: var(--space-sm);
}
.batch-area .glass-input {
  padding: 6px var(--space-sm);
  font-size: 12px;
}

.action-btn {
  width: 100%;
  padding: 10px;
  border: none;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  margin-top: var(--space-sm);
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.accent-btn {
  background: linear-gradient(135deg, var(--accent), #7c3aed);
  color: white;
}
.accent-btn:hover:not(:disabled) {
  box-shadow: 0 0 20px var(--accent-glow);
  transform: translateY(-1px);
}
.ghost-btn {
  background: var(--bg-hover);
  color: var(--text-secondary);
}
.ghost-btn:hover:not(:disabled) {
  background: var(--border);
  color: var(--text-primary);
}
.ghost-btn.small {
  font-size: 12px;
  padding: 8px;
  font-weight: 400;
}

.progress-bar-container { margin-bottom: var(--space-sm); }
.progress-bar {
  height: 4px;
  background: var(--bg-hover);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  border-radius: 2px;
  transition: width 0.5s ease;
}
.progress-text {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

.streaming-indicator {
  font-size: 12px;
  color: var(--accent);
  text-align: center;
  padding: var(--space-sm);
}

.sidebar-spacer { flex: 1; }

.sidebar-footer {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding-top: var(--space-md);
  border-top: 1px solid var(--border);
}

.model-select {
  padding: 6px var(--space-sm);
  font-size: 12px;
  cursor: pointer;
}
</style>
