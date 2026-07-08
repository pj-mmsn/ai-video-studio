<template>
  <div class="world-panel">
    <div v-if="content" class="world-content glass-card">
      <h4>🌍 世界观设定</h4>
      <p>{{ content }}</p>
    </div>
    <div v-else class="empty-content">
      <span class="empty-icon">🌍</span>
      <p>暂无世界观设定，请先生成构思</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  content: { type: String, default: '' },
})
</script>

<style scoped>
.world-panel {
  padding: var(--space-md);
  height: 100%;
}
.world-content {
  padding: var(--space-lg);
}
.world-content h4 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: var(--space-sm);
  color: var(--accent);
}
.world-content p {
  font-size: 14px;
  line-height: 1.8;
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
.empty-icon { font-size: 48px; opacity: 0.5; }
</style>
