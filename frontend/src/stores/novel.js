import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, streamSSE } from '../api/index.js'

export const useNovelStore = defineStore('novel', () => {
  // ============ 状态 ============
  const mode = ref('idea')           // idea | outline | write | review
  const novelId = ref(null)
  const novel = ref(null)            // { id, title, genre, premise, ... }
  const idea = ref({})               // 构思结果 { title, genre, premise, world_building, characters, hook }
  const outlineTree = ref([])        // 大纲树 [{ volume_title, chapters: [{ chapter_title, sections: [...] }] }]
  const selectedNodeId = ref(null)   // 当前选中的大纲节点 ID
  const sectionContent = ref('')     // 当前节正文
  const isStreaming = ref(false)
  const streamBuffer = ref('')       // 流式缓冲
  const progress = ref({ done: 0, total: 0, words: 0, pct: 0 })
  const reviewReport = ref('')       // 审稿报告
  const error = ref(null)

  // ============ 计算属性 ============
  const currentModeLabel = computed(() => ({
    idea: '💡 构思', outline: '📋 大纲', write: '✍️ 写作', review: '🔍 审稿'
  }[mode.value] || ''))

  const isWriting = computed(() => isStreaming.value && (mode.value === 'write' || mode.value === 'idea' || mode.value === 'outline'))

  // ============ 项目管理 ============
  async function loadProjects() {
    return api('/api/novels')
  }

  async function createNovel() {
    const data = await api('/api/novels', { method: 'POST', body: JSON.stringify({}) })
    novelId.value = data.id
    return data
  }

  async function loadNovel(id) {
    novelId.value = id
    const data = await api(`/api/novels/${id}`)
    novel.value = data.novel
    idea.value = {
      title: data.novel?.title || '',
      genre: data.novel?.genre || '',
      premise: data.novel?.premise || '',
      world_building: data.world_building || '',
      characters: data.characters || [],
    }
    await loadOutline()
    await loadProgress()
  }

  // ============ 构思 ============
  async function* generateIdea(ideaText) {
    isStreaming.value = true
    streamBuffer.value = ''
    error.value = null
    try {
      const stream = streamSSE(`/api/novels/${novelId.value}/idea`, { idea: ideaText })
      for await (const chunk of stream) {
        if (chunk.type === 'chunk') {
          streamBuffer.value += chunk.text
          yield { type: 'chunk', text: chunk.text }
        } else if (chunk.type === 'done') {
          idea.value = chunk.data
          novel.value = { ...novel.value, title: chunk.data.title, genre: chunk.data.genre, premise: chunk.data.premise }
          yield { type: 'done', data: chunk.data }
        }
      }
    } catch (e) {
      error.value = e.message
      yield { type: 'error', message: e.message }
    } finally {
      isStreaming.value = false
    }
  }

  // ============ 大纲 ============
  async function* generateOutline(volumes, chaptersPerVol) {
    isStreaming.value = true
    streamBuffer.value = ''
    error.value = null
    try {
      const stream = streamSSE(`/api/novels/${novelId.value}/outline`, { volumes, chapters_per_vol: chaptersPerVol })
      for await (const chunk of stream) {
        if (chunk.type === 'chunk') {
          streamBuffer.value += chunk.text
          yield { type: 'chunk', text: chunk.text }
        } else if (chunk.type === 'done') {
          await loadOutline()
          yield { type: 'done' }
        }
      }
    } catch (e) {
      error.value = e.message
      yield { type: 'error', message: e.message }
    } finally {
      isStreaming.value = false
    }
  }

  async function loadOutline() {
    const data = await api(`/api/novels/${novelId.value}/outline`)
    outlineTree.value = data.tree || []
  }

  async function updateOutlineNode(nodeId, updates) {
    await api(`/api/novels/${novelId.value}/outline/${nodeId}`, {
      method: 'PUT', body: JSON.stringify(updates)
    })
    await loadOutline()
  }

  async function deleteOutlineNode(nodeId) {
    await api(`/api/novels/${novelId.value}/outline/${nodeId}`, { method: 'DELETE' })
    await loadOutline()
  }

  async function batchReplaceOutline(find, replace) {
    return api(`/api/novels/${novelId.value}/outline/batch-replace`, {
      method: 'POST', body: JSON.stringify({ find, replace })
    })
  }

  // ============ 写作 ============
  async function selectNode(nodeId) {
    selectedNodeId.value = nodeId
    try {
      const data = await api(`/api/novels/${novelId.value}/sections/${nodeId}`)
      sectionContent.value = data.content || ''
    } catch {
      sectionContent.value = ''
    }
  }

  async function* writeSection(feedback = '') {
    isStreaming.value = true
    streamBuffer.value = ''
    error.value = null
    try {
      const stream = streamSSE(`/api/novels/${novelId.value}/write/${selectedNodeId.value}`, { feedback })
      for await (const chunk of stream) {
        if (chunk.type === 'chunk') {
          streamBuffer.value += chunk.text
          yield { type: 'chunk', text: chunk.text }
        } else if (chunk.type === 'done') {
          sectionContent.value = chunk.content || streamBuffer.value
          await loadProgress()
          await loadOutline()
          yield { type: 'done' }
        }
      }
    } catch (e) {
      error.value = e.message
      yield { type: 'error', message: e.message }
    } finally {
      isStreaming.value = false
    }
  }

  // ============ 审稿 ============
  async function* reviewNovel() {
    isStreaming.value = true
    streamBuffer.value = ''
    reviewReport.value = ''
    error.value = null
    try {
      const stream = streamSSE(`/api/novels/${novelId.value}/review`)
      for await (const chunk of stream) {
        if (chunk.type === 'chunk') {
          streamBuffer.value += chunk.text
          yield { type: 'chunk', text: chunk.text }
        } else if (chunk.type === 'done') {
          reviewReport.value = chunk.content || streamBuffer.value
          yield { type: 'done' }
        }
      }
    } catch (e) {
      error.value = e.message
      yield { type: 'error', message: e.message }
    } finally {
      isStreaming.value = false
    }
  }

  // ============ 角色 ============
  async function addCharacter(char) {
    await api(`/api/novels/${novelId.value}/characters`, {
      method: 'POST', body: JSON.stringify(char)
    })
    await refreshCharacters()
  }

  async function updateCharacter(charId, char) {
    await api(`/api/novels/${novelId.value}/characters/${charId}`, {
      method: 'PUT', body: JSON.stringify(char)
    })
    await refreshCharacters()
  }

  async function deleteCharacter(charId) {
    await api(`/api/novels/${novelId.value}/characters/${charId}`, { method: 'DELETE' })
    await refreshCharacters()
  }

  async function refreshCharacters() {
    const data = await api(`/api/novels/${novelId.value}/characters`)
    idea.value.characters = data.characters || []
  }

  // ============ 导出 ============
  function getExportUrl(format) {
    return `/api/novels/${novelId.value}/export?format=${format}`
  }

  async function getFulltext() {
    return api(`/api/novels/${novelId.value}/fulltext`)
  }

  // ============ 进度 ============
  async function loadProgress() {
    try {
      const data = await api(`/api/novels/${novelId.value}`)
      progress.value = data.progress || { done: 0, total: 0, words: 0, pct: 0 }
    } catch { /* ignore */ }
  }

  // ============ 清空 ============
  function reset() {
    mode.value = 'idea'
    novelId.value = null
    novel.value = null
    idea.value = {}
    outlineTree.value = []
    selectedNodeId.value = null
    sectionContent.value = ''
    streamBuffer.value = ''
    reviewReport.value = ''
    progress.value = { done: 0, total: 0, words: 0, pct: 0 }
    error.value = null
  }

  return {
    // state
    mode, novelId, novel, idea, outlineTree, selectedNodeId,
    sectionContent, isStreaming, streamBuffer, progress, reviewReport, error,
    // computed
    currentModeLabel, isWriting,
    // actions
    loadProjects, createNovel, loadNovel,
    generateIdea, generateOutline, loadOutline, updateOutlineNode, deleteOutlineNode, batchReplaceOutline,
    selectNode, writeSection,
    reviewNovel,
    addCharacter, updateCharacter, deleteCharacter,
    getExportUrl, getFulltext,
    loadProgress,
    reset,
  }
})
