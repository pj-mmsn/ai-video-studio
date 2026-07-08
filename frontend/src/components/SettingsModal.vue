<template>
  <div class="overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="hd">
        <h3>⚙️ 设置</h3>
        <button class="x" @click="$emit('close')">✕</button>
      </div>

      <!-- 字体大小 -->
      <div class="sec">
        <div class="sec-label">字体大小</div>
        <div class="font-row">
          <span class="fs-sm">A</span>
          <input type="range" :min="12" :max="24" :step="1" v-model.number="settings.fontSize">
          <span class="fs-lg">A</span>
          <span class="fs-val">{{ settings.fontSize }}px</span>
        </div>
        <div class="preview" :style="{fontSize:settings.fontSize+'px'}">
          预览文字 — 这是正文的显示效果
        </div>
      </div>

      <!-- 视频背景 -->
      <div class="sec">
        <div class="sec-label">🎬 视频背景</div>
        <div class="bg-grid">
          <div v-for="v in videos" :key="v.key"
            :class="['bg-card',{on:settings.bgVideo===v.key}]"
            @click="settings.bgVideo=v.key">
            <div class="bg-preview video-preview">{{ v.label.slice(0,2) }}</div>
            <div class="bg-info">
              <div class="bg-name">{{ v.label }}</div>
              <div class="bg-desc">{{ v.desc }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 粒子背景 -->
      <div class="sec">
        <div class="sec-label">粒子效果</div>
        <div class="bg-grid">
          <div v-for="b in backgrounds" :key="b.key"
            :class="['bg-card',{on:settings.background===b.key}]"
            @click="settings.background=b.key">
            <div class="bg-preview" :class="'bg-'+b.key"></div>
            <div class="bg-info">
              <div class="bg-name">{{ b.label }}</div>
              <div class="bg-desc">{{ b.desc }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="ft">
        <button class="b2" @click="reset">恢复默认</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useSettings } from '../stores/settings.js'
const { settings, backgrounds, videos, reset } = useSettings()
defineEmits(['close'])
</script>

<style scoped>
.overlay{position:fixed;inset:0;z-index:500;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:18px;width:440px;max-height:80vh;overflow-y:auto;padding:28px;box-shadow:0 16px 64px rgba(0,0,0,.4)}

.hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}
.hd h3{font-size:18px;font-weight:650}
.x{width:32px;height:32px;border:none;border-radius:8px;background:transparent;color:var(--text2);font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center}.x:hover{background:var(--surface2);color:var(--text)}

.sec{margin-bottom:24px}
.sec-label{font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px}

.font-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.font-row input[type=range]{flex:1;accent-color:var(--accent)}
.fs-sm{font-size:10px;color:var(--text3)}.fs-lg{font-size:18px;color:var(--text3)}.fs-val{font-size:12px;color:var(--text2);min-width:36px;text-align:right}

.preview{padding:12px;background:var(--surface2);border-radius:10px;color:var(--text);line-height:1.8}

.bg-grid{display:flex;flex-direction:column;gap:6px}
.bg-card{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:12px;cursor:pointer;border:1px solid transparent;transition:.12s}
.bg-card:hover{background:var(--surface2)}
.bg-card.on{border-color:var(--accent);background:var(--accent-dim)}
.bg-preview{width:48px;height:32px;border-radius:6px;flex-shrink:0}
.bg-particles{background:radial-gradient(circle at 30% 50%,rgba(129,140,248,.6),#0c0c14)}
.bg-minimal{background:#0c0c14;border:1px solid var(--border)}
.video-preview{display:flex;align-items:center;justify-content:center;font-size:18px;background:linear-gradient(135deg,#1a1a35,#0d0d1f);border:1px solid var(--border)}
.bg-name{font-size:13px;font-weight:550;color:var(--text)}
.bg-desc{font-size:11px;color:var(--text3);margin-top:1px}

.ft{padding-top:12px;border-top:1px solid var(--border)}
.b2{padding:8px 18px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--text2);font-size:12px;cursor:pointer}.b2:hover{background:var(--surface2)}
</style>
