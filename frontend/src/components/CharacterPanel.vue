<template>
  <div class="character-panel">
    <div class="char-actions">
      <button class="action-btn ghost-btn small" @click="$emit('add')">＋ 添加</button>
    </div>

    <div v-if="characters.length === 0" class="char-empty">
      <p>暂无角色</p>
      <p class="hint">构思完成后自动生成，或手动添加</p>
    </div>

    <div v-else class="char-list">
      <div
        v-for="(char, i) in characters"
        :key="i"
        class="char-card glass-card"
        @dblclick="$emit('edit', char)"
      >
        <div class="char-header">
          <h4>{{ char.name }}</h4>
          <span class="char-role">{{ char.role }}</span>
        </div>
        <p class="char-traits" v-if="char.traits">{{ char.traits }}</p>
        <div class="char-details">
          <div v-if="char.desire" class="char-detail">
            <span class="detail-label">🎯 欲望</span>
            <span>{{ char.desire }}</span>
          </div>
          <div v-if="char.fear" class="char-detail">
            <span class="detail-label">😰 恐惧</span>
            <span>{{ char.fear }}</span>
          </div>
        </div>
        <div class="char-footer">
          <button class="mini-btn" @click.stop="$emit('edit', char)">✏</button>
          <button class="mini-btn danger" @click.stop="$emit('delete', char)">🗑</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  characters: { type: Array, default: () => [] },
})
defineEmits(['add', 'edit', 'delete'])
</script>

<style scoped>
.character-panel {
  padding: var(--space-md);
  height: 100%;
  overflow-y: auto;
}

.char-actions {
  margin-bottom: var(--space-md);
}

.char-empty {
  text-align: center;
  color: var(--text-muted);
  padding: var(--space-xl);
}
.char-empty .hint {
  font-size: 12px;
  opacity: 0.7;
  margin-top: 4px;
}

.char-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.char-card {
  padding: var(--space-md);
  position: relative;
}
.char-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-xs);
}
.char-header h4 {
  font-size: 15px;
  font-weight: 600;
}
.char-role {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--accent-glow);
  color: var(--accent);
}

.char-traits {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: var(--space-xs);
}

.char-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.char-detail {
  font-size: 12px;
  color: var(--text-muted);
}
.detail-label {
  color: var(--text-secondary);
  margin-right: 4px;
}

.char-footer {
  position: absolute;
  top: var(--space-sm);
  right: var(--space-sm);
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.char-card:hover .char-footer {
  opacity: 1;
}

.mini-btn {
  padding: 2px 6px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  transition: all var(--transition-fast);
}
.mini-btn:hover { background: var(--border); color: var(--text-primary); }
.mini-btn.danger:hover { background: rgba(248, 113, 113, 0.2); color: var(--error); }
</style>
