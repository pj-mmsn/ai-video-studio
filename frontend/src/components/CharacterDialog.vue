<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog glass-card animate-in">
      <h3>{{ data?.id ? '✏ 编辑角色' : '＋ 添加角色' }}</h3>
      <div class="dialog-body">
        <div v-for="f in fields" :key="f.key" class="field">
          <label>{{ f.label }}</label>
          <input
            v-model="form[f.key]"
            class="glass-input"
            :placeholder="f.placeholder"
          />
        </div>
      </div>
      <div class="dialog-footer">
        <button class="btn-ghost" @click="$emit('close')">取消</button>
        <button class="btn-accent" @click="handleSave">保存</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  data: { type: Object, default: null },
})
const emit = defineEmits(['save', 'close'])

const fields = [
  { key: 'name', label: '角色名', placeholder: '姓名' },
  { key: 'role', label: '身份', placeholder: '主角/配角/反派' },
  { key: 'traits', label: '性格特征', placeholder: '性格+外貌 20字内' },
  { key: 'desire', label: '欲望', placeholder: '想要什么' },
  { key: 'fear', label: '恐惧', placeholder: '怕什么' },
]

const form = ref({
  name: '', role: '', traits: '', desire: '', fear: '',
})

watch(() => props.data, (val) => {
  if (val) {
    form.value = { ...form.value, ...val }
  } else {
    form.value = { name: '', role: '', traits: '', desire: '', fear: '' }
  }
}, { immediate: true })

function handleSave() {
  if (!form.value.name.trim()) return
  emit('save', { ...form.value, id: props.data?.id })
}
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
  width: 400px;
  max-height: 80vh;
  overflow-y: auto;
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
.field label {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.field input {
  width: 100%;
  padding: 8px var(--space-sm);
  font-size: 13px;
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
  transition: all var(--transition-fast);
}
.btn-accent:hover { box-shadow: 0 0 20px var(--accent-glow); }
</style>
