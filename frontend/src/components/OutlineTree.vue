<template>
  <div class="outline-tree">
    <div class="tree-header">
      <h3>📑 大纲目录</h3>
      <span class="tree-hint">{{ nodeCount }} 节</span>
    </div>
    <div class="tree-body">
      <n-tree
        v-if="treeData.length > 0"
        :data="treeData"
        :selected-keys="selectedId ? [selectedId] : []"
        :expanded-keys="expandedKeys"
        :node-props="nodeProps"
        block-line
        selectable
        @update:selected-keys="handleSelect"
        @update:expanded-keys="expandedKeys = $event"
      />
      <div v-else class="tree-empty">
        <p>暂无大纲</p>
        <p class="hint">先生成构思，再生成大纲</p>
      </div>
    </div>

    <!-- 右键菜单 -->
    <div
      v-if="contextMenu.visible"
      class="context-menu glass-card"
      :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
    >
      <button @click="handleAction('rename')">✏ 改标题</button>
      <button @click="handleAction('summary')">📝 改概要</button>
      <hr />
      <button @click="handleAction('toggle')">
        {{ contextMenu.status === 'done' ? '○ 标记待写' : '✓ 标记完成' }}
      </button>
      <hr />
      <button class="danger" @click="handleAction('delete')">🗑 删除此节</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { NTree } from 'naive-ui'

const props = defineProps({
  tree: { type: Array, default: () => [] },
  selectedId: { type: [Number, null], default: null },
})

const emit = defineEmits(['select', 'rename', 'edit-summary', 'toggle-status', 'delete'])

const expandedKeys = ref([])
const contextMenu = ref({ visible: false, x: 0, y: 0, nodeId: null, status: '' })

// 将平铺数据转为 Naive UI Tree 需要的嵌套格式
const treeData = computed(() => {
  return buildTree(props.tree)
})

const nodeCount = computed(() => {
  let count = 0
  props.tree.forEach(v => {
    v.chapters?.forEach(ch => {
      count += (ch.sections || []).length
    })
  })
  return count
})

function buildTree(nodes) {
  const result = []
  nodes.forEach(vol => {
    const volChildren = []
    vol.chapters?.forEach(ch => {
      const secChildren = (ch.sections || []).map(sec => ({
        key: sec.id,
        label: `${sec.status === 'done' ? '✓ ' : ''}${sec.section_title || `第${sec.section_order}节`}`,
        isLeaf: true,
      }))
      volChildren.push({
        key: `ch_${ch.chapter_title}`,
        label: ch.chapter_title || '未命名章',
        children: secChildren,
      })
    })
    result.push({
      key: `vol_${vol.volume_title}`,
      label: vol.volume_title || '未命名卷',
      children: volChildren,
    })
  })
  return result
}

function nodeProps({ option }) {
  return {
    onContextmenu(e) {
      e.preventDefault()
      if (option.isLeaf) {
        contextMenu.value = {
          visible: true,
          x: e.clientX,
          y: e.clientY,
          nodeId: option.key,
          status: option.label?.startsWith('✓ ') ? 'done' : 'pending',
        }
      }
    },
  }
}

function handleSelect(keys) {
  const id = keys[0]
  if (id && typeof id === 'number') {
    emit('select', id)
  }
  contextMenu.value.visible = false
}

function handleAction(action) {
  const nodeId = contextMenu.value.nodeId
  contextMenu.value.visible = false

  if (action === 'rename') {
    const title = prompt('新标题:')
    if (title) emit('rename', nodeId, title)
  } else if (action === 'summary') {
    const summary = prompt('新概要:')
    if (summary) emit('edit-summary', nodeId, summary)
  } else if (action === 'toggle') {
    emit('toggle-status', nodeId, contextMenu.value.status)
  } else if (action === 'delete') {
    if (confirm('确定删除此节？')) emit('delete', nodeId)
  }
}

// 初始展开所有节点
watch(() => props.tree, () => {
  const keys = []
  props.tree.forEach(vol => {
    keys.push(`vol_${vol.volume_title}`)
    vol.chapters?.forEach(ch => {
      keys.push(`ch_${ch.chapter_title}`)
    })
  })
  expandedKeys.value = keys
}, { immediate: true, deep: true })
</script>

<style scoped>
.outline-tree {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--border);
}
.tree-header h3 {
  font-size: 14px;
  font-weight: 600;
}
.tree-hint {
  font-size: 11px;
  color: var(--text-muted);
}

.tree-body {
  flex: 1;
  overflow: auto;
  padding: var(--space-sm);
}

.tree-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: var(--space-sm);
}
.tree-empty .hint {
  font-size: 12px;
  opacity: 0.7;
}

.context-menu {
  position: fixed;
  z-index: 200;
  padding: var(--space-xs);
  min-width: 150px;
}
.context-menu button {
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}
.context-menu button:hover {
  background: var(--bg-hover);
}
.context-menu button.danger {
  color: var(--error);
}
.context-menu hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 4px 0;
}
</style>
