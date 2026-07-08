import { ref, watch, reactive } from 'vue'

const defaults = {
  fontSize: 16,
  background: 'particles',
  bgVideo: 'sea-eye',
}

const state = reactive({ ...defaults })

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem('ai-novelist-settings'))
    if (saved) Object.assign(state, saved)
  } catch {}
}
load()

watch(() => ({ ...state }), (v) => {
  localStorage.setItem('ai-novelist-settings', JSON.stringify(v))
}, { deep: true })

export function useSettings() {
  function reset() { Object.assign(state, defaults) }

  return {
    settings: state,
    reset,
    backgrounds: [
      { key: 'particles', label: '✨ 粒子星空', desc: '浮动光点 + 连线' },
      { key: 'minimal', label: '⬛ 极简纯色', desc: '无背景动画' },
    ],
    videos: [
      { key: 'sea-eye', label: '🌊 海的眼睛', desc: '深邃海洋' },
      { key: 'lotus', label: '🪷 莲华', desc: '静谧唯美' },
      { key: 'snow', label: '❄️ 雪中', desc: '冬日暖阳' },
      { key: 'mononoke', label: '🌿 幽灵公主', desc: '唯美雪景' },
    ],
  }
}
