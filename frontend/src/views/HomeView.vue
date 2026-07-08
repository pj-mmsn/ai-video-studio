<template>
  <div class="wrap">
    <div class="card">
      <div class="brand">
        <button class="gear" @click="showSettings=true">⚙️</button>
        <div class="logo">
          <span class="logo-inner">✍️</span>
        </div>
        <h1>AI 小说家</h1>
        <p>AI 驱动的长篇小说创作助手</p>
      </div>

      <button class="btn" @click="create" :disabled="loading">
        <span v-if="!loading">✨ 开始新的创作</span>
        <span v-else class="sp"></span>
      </button>

      <div v-if="projects.length" class="section">
        <div class="section-hd">
          <span>继续创作</span>
          <span class="section-count">{{ projects.length }} 个项目</span>
        </div>
        <div class="list">
          <div v-for="p in projects" :key="p.id" class="item" @click="router.push('/novel/'+p.id)">
            <div class="item-avatar" :style="{background: gradients[p.id] || gradients._default}">
              {{ (p.title||'?')[0] }}
            </div>
            <div class="item-info">
              <div class="item-title">{{ p.title||'未命名' }}</div>
              <div class="item-meta">
                <span v-if="p.genre">{{ p.genre }}</span>
                <span v-if="p.words" class="item-words">{{ (p.words||0).toLocaleString() }} 字</span>
              </div>
            </div>
            <div class="item-actions">
              <button class="del" @click.stop="remove(p)" title="删除">🗑</button>
              <span class="arrow">→</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="error" class="err">{{ error }}</div>
      <div class="footer">
        <span>v3.0</span>
        <span class="footer-dot">·</span>
        <span>Powered by DeepSeek</span>
      </div>
    </div>

    <SettingsModal v-if="showSettings" @close="showSettings=false" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import SettingsModal from '../components/SettingsModal.vue'
import { useSettings } from '../stores/settings.js'
const router=useRouter(),{settings}=useSettings(),projects=ref([]),loading=ref(false),error=ref(''),showSettings=ref(false)

const gradients = {
  _default: 'linear-gradient(135deg,#818cf8,#6366f1)',
  [Symbol()]: 'linear-gradient(135deg,#818cf8,#6366f1)',
}

const palette = [
  'linear-gradient(135deg,#818cf8,#6366f1)',
  'linear-gradient(135deg,#6ee7b7,#34d399)',
  'linear-gradient(135deg,#fbbf24,#f59e0b)',
  'linear-gradient(135deg,#f472b6,#ec4899)',
  'linear-gradient(135deg,#38bdf8,#0ea5e9)',
  'linear-gradient(135deg,#a78bfa,#8b5cf6)',
]

onMounted(async()=>{
  try{
    const d=await (await fetch('/api/novels')).json()
    projects.value = d.map((p,i) => ({...p, _grad: palette[i % palette.length]}))
  }catch{error.value='加载失败'}
})

async function create(){loading.value=true;try{const r=await fetch('/api/novels',{method:'POST'});router.push('/novel/'+(await r.json()).id)}catch{error.value='创建失败';loading.value=false}}

async function remove(p){
  if(!confirm(`确定删除「${p.title||'未命名'}」？此操作不可恢复。`))return
  try{await fetch('/api/novels/'+p.id,{method:'DELETE'});projects.value=projects.value.filter(x=>x.id!==p.id)}catch{error.value='删除失败'}
}
</script>

<style scoped>
.wrap{position:relative;z-index:1;height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}

.card{
  background:rgba(19,19,42,.75);backdrop-filter:blur(30px);-webkit-backdrop-filter:blur(30px);
  border:1px solid rgba(255,255,255,.06);border-radius:24px;
  padding:48px 44px 32px;width:100%;max-width:520px;
  box-shadow:0 8px 40px rgba(0,0,0,.5),0 0 0 1px rgba(139,140,248,.05);
  animation:card-in .6s ease backwards;
  position:relative;overflow:hidden;
}
.card::before{
  content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent,var(--accent),var(--accent2),transparent);
}
@keyframes card-in{from{opacity:0;transform:translateY(20px) scale(.98)}to{opacity:1;transform:translateY(0) scale(1)}}

/* Brand */
.brand{text-align:center;margin-bottom:32px;position:relative}
.gear{position:absolute;top:0;right:0;width:36px;height:36px;border:none;border-radius:10px;background:rgba(255,255,255,.04);color:var(--text3);font-size:16px;cursor:pointer;transition:.15s;display:flex;align-items:center;justify-content:center}
.gear:hover{background:rgba(255,255,255,.08);color:var(--text2)}
.logo{width:80px;height:80px;margin:0 auto 16px;border-radius:50%;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 40px rgba(139,140,248,.3);
  animation:logo-float 4s ease-in-out infinite;
}
@keyframes logo-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
.logo-inner{font-size:34px;line-height:1;filter:drop-shadow(0 2px 4px rgba(0,0,0,.3))}
h1{font-size:30px;font-weight:800;letter-spacing:-.5px;margin-bottom:6px;background:linear-gradient(135deg,#e8e6f0,#a09cb8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.brand p{color:var(--text3);font-size:13px}

/* Create button */
.btn{
  width:100%;padding:15px;border:none;border-radius:14px;
  background:linear-gradient(135deg,var(--accent),#6366f1);
  color:#fff;font-size:15px;font-weight:600;cursor:pointer;
  transition:.2s;margin-bottom:32px;
  box-shadow:0 4px 24px rgba(99,102,241,.4);
  display:flex;align-items:center;justify-content:center;gap:8px;
}
.btn:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(99,102,241,.55)}
.btn:disabled{opacity:.5;cursor:default;transform:none}
.sp{width:18px;height:18px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* Section */
.section{margin-bottom:12px}
.section-hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.section-hd span:first-child{font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.6px}
.section-count{font-size:10px;color:var(--text3);background:rgba(255,255,255,.04);padding:2px 8px;border-radius:6px}

/* Project items */
.list{display:flex;flex-direction:column;gap:6px}
.item{
  display:flex;align-items:center;gap:14px;padding:12px 14px;border-radius:14px;
  cursor:pointer;transition:.15s;position:relative;
  background:rgba(255,255,255,.02);border:1px solid transparent;
}
.item:hover{background:rgba(255,255,255,.05);border-color:rgba(255,255,255,.06);transform:translateX(3px)}

.item-avatar{
  width:44px;height:44px;border-radius:14px;
  display:flex;align-items:center;justify-content:center;
  font-size:18px;font-weight:700;color:#fff;flex-shrink:0;
  box-shadow:0 4px 12px rgba(0,0,0,.3);
  transition:.15s;
}
.item:hover .item-avatar{transform:scale(1.05)}

.item-info{flex:1;min-width:0}
.item-title{font-size:14px;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:2px}
.item-meta{display:flex;gap:8px;font-size:11px;color:var(--text3)}
.item-words{color:var(--accent);font-weight:500}

.item-actions{display:flex;align-items:center;gap:4px;flex-shrink:0}
.del{
  width:30px;height:30px;border:none;border-radius:8px;background:transparent;
  color:var(--text3);font-size:13px;cursor:pointer;display:flex;align-items:center;justify-content:center;
  transition:.12s;opacity:0;
}
.item:hover .del{opacity:1}
.del:hover{background:rgba(251,113,133,.15);color:#fb7185}
.arrow{color:var(--text3);font-size:16px;transition:.12s}
.item:hover .arrow{color:var(--text);transform:translateX(3px)}

/* Footer */
.footer{text-align:center;padding-top:20px;font-size:10px;color:var(--text3)}
.footer-dot{margin:0 4px}

.err{color:var(--red);font-size:12px;text-align:center;margin-top:8px}
</style>
