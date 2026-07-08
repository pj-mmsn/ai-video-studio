<template>
  <div class="ws">
    <!-- Loading -->
    <div v-if="loading" class="ld">
      <div class="ld-spinner"></div>
      <div class="ld-text">加载项目...</div>
    </div>

    <!-- Error -->
    <div v-else-if="err" class="ld">
      <div class="err-icon">!</div>
      <div class="err-msg">{{ err }}</div>
      <button class="btn-back" @click="router.push('/')">← 返回首页</button>
    </div>

    <template v-else>
      <!-- ═══ 侧边栏 ═══ -->
      <aside class="sb" :style="{width:sbW+'px'}">
        <div class="sb-top">
          <div class="back" @click="router.push('/')">← 返回</div>
          <div class="name">{{ novel?.title||'未命名' }}</div>
          <div class="genre" v-if="novel?.genre">{{ novel.genre }}</div>
        </div>

        <nav class="nav">
          <button v-for="m in modes" :key="m.k"
            :class="['nb',{on:mode===m.k}]" @click="mode=m.k">
            <span class="nb-i">{{ m.i }}</span>
            <span class="nb-l">{{ m.l }}</span>
            <span class="nb-hint" v-if="m.k==='write'">{{ progDone }}/{{ progTotal }}</span>
          </button>
        </nav>

        <!-- 统计卡片 -->
        <div class="stats">
          <div class="stat" :class="{pulse:statPulse.words}"><span class="st-n">{{ (progWords||0).toLocaleString() }}</span><span class="st-l">总字数</span></div>
          <div class="stat" :class="{pulse:statPulse.chars}"><span class="st-n">{{ chars.length }}</span><span class="st-l">角色</span></div>
          <div class="stat" :class="{pulse:statPulse.prog}"><span class="st-n">{{ progDone }}/{{ progTotal }}</span><span class="st-l">进度</span></div>
        </div>

        <div class="panel">
          <!-- 构思 -->
          <div v-if="mode==='idea'" class="pm">
            <textarea v-model="ideaText" placeholder="输入故事灵感..." rows="3"></textarea>
            <button class="b1" @click="doIdea" :disabled="busy">
              <span v-if="!busy">💡 生成构思</span>
              <span v-else class="sp"></span>
            </button>
          </div>

          <!-- 大纲 -->
          <div v-if="mode==='outline'" class="pm">
            <div class="kv"><span>卷数</span><input v-model.number="vols" type="number" min="1" max="20"></div>
            <div class="kv"><span>每卷章数</span><input v-model.number="chaps" type="number" min="1" max="20"></div>
            <button class="b1" @click="doOutline" :disabled="busy">
              <span v-if="!busy">📋 生成大纲</span>
              <span v-else class="sp"></span>
            </button>
          </div>

          <!-- 写作 -->
          <div v-if="mode==='write'" class="pm">
            <div class="pg-wrap">
              <div class="pg"><div class="pgf" :style="{width:progPct+'%'}"></div></div>
              <div class="pgt">{{ progPct }}% · {{ (progWords||0).toLocaleString() }}字</div>
            </div>
            <button class="b1 b-auto" @click="doAutoWrite" :disabled="busy">
              <span v-if="!busy">🤖 自动续写</span>
              <span v-else class="sp"></span>
            </button>
          </div>

          <!-- 审稿 -->
          <div v-if="mode==='review'" class="pm">
            <p class="review-hint">AI 将对照大纲逐节审核全文，指出逻辑矛盾、情节断层和节奏问题。</p>
            <button class="b1" @click="doReview" :disabled="busy">
              <span v-if="!busy">🔍 开始审稿</span>
              <span v-else class="sp"></span>
            </button>
          </div>
        </div>

        <div class="foot">
          <button class="b2" @click="showSettings=true">⚙️ 设置</button>
          <button class="b2" @click="exportNovel">📥 导出</button>
        </div>
      </aside>

      <div class="grip" @mousedown="startDrag('sb',$event)"></div>

      <!-- ═══ 目录 ═══ -->
      <div class="ct" :style="{width:ctW+'px'}">
        <div class="cth">
          <span>📑 目录</span>
          <span class="ctn">{{ nodeCount }}节</span>
        </div>
        <div class="ctb">
          <div v-if="!outline.length" class="emp">
            <div class="emp-icon">📋</div>
            <div>暂无大纲</div>
            <div class="emp-sub">先完成构思和大纲生成</div>
          </div>
          <div v-for="v in outline" :key="v.volume_title" class="toc-vol">
            <div class="tv" @click="v._open=!v._open">
              <span class="tv-arrow">{{ v._open!==false?'▾':'▸' }}</span>
              {{ v.volume_title }}
            </div>
            <template v-if="v._open!==false">
              <div v-for="ch in v.chapters" :key="ch.chapter_title" class="toc-ch">
                <div class="tc">{{ ch.chapter_title }}</div>
                <div v-for="s in ch.sections" :key="s.id"
                  :class="['ts',{
                    sel:sel===s.id,
                    done:s.status==='done',
                    writing:autoWriting && autoNodeId===s.id
                  }]"
                  @click="pick(s.id)">
                  <span class="ts-dot" :class="s.status"></span>
                  <span class="ts-name">{{ s.section_title||'第'+s.section_order+'节' }}</span>
                  <span class="ts-wc" v-if="s._wc">{{ s._wc }}字</span>
                </div>
              </div>
            </template>
          </div>
        </div>
        <div class="ctf">
          <input v-model="fb" placeholder="修改意见（可留空）" @keydown.enter="doWrite" :disabled="busy">
          <button class="b1 b-exec" @click="doWrite" :disabled="busy||!sel">
            {{ busy?'⏳':'✍️ 执行' }}
          </button>
        </div>
      </div>

      <div class="grip" @mousedown="startDrag('ct',$event)"></div>

      <!-- ═══ 内容区 ═══ -->
      <div class="rt">
        <div class="rtt">
          <button :class="['rtb',{on:tab==='c'}]" @click="tab='c'">
            <span class="rtb-i">📄</span> 内容
          </button>
          <button :class="['rtb',{on:tab==='f'}]" @click="tab='f';loadFulltext()">
            <span class="rtb-i">📚</span> 全文
          </button>
          <button :class="['rtb',{on:tab==='r'}]" @click="tab='r'">
            <span class="rtb-i">👥</span> 角色
          </button>
          <button :class="['rtb',{on:tab==='w'}]" @click="tab='w'">
            <span class="rtb-i">🌍</span> 世界观
          </button>
        </div>

        <!-- 内容 -->
        <div class="rtc" ref="cz" :style="{fontSize:settings.fontSize+'px'}">
          <!-- 加载动画 -->
          <div v-if="generating" class="gen-overlay">
            <div class="gen-spinner"></div>
            <div class="gen-text">
              <template v-if="generating==='idea'">💡 正在生成构思...</template>
              <template v-else-if="generating==='outline'">📋 正在生成大纲...</template>
              <template v-else-if="generating==='review'">🔍 正在审稿分析...</template>
              <template v-else>⏳ 处理中...</template>
            </div>
            <div class="gen-sub">AI 正在思考，请稍候</div>
          </div>

          <!-- 自动续写面板 -->
          <div v-if="autoWriting && tab==='c'" class="auto-panel">
            <div class="auto-hd">
              <span class="auto-title">🤖 自动续写中</span>
              <span class="auto-progress">{{ autoIdx }}/{{ autoTotal }} 节</span>
            </div>
            <div class="auto-dots">
              <span v-for="i in autoTotal" :key="i"
                :class="['ad',{done:i<=autoDone,cur:i===autoIdx}]"></span>
            </div>
            <div class="auto-cur" v-if="autoCurTitle">{{ autoCurTitle }}</div>
            <div class="auto-stats">
              <span>已写 {{ autoDoneWords.toLocaleString() }} 字</span>
              <span v-if="autoLastAnalysis">{{ autoLastAnalysis }}</span>
            </div>
            <div class="auto-text">{{ stream }}</div>
          </div>

          <!-- 普通内容 -->
          <template v-else-if="tab==='c'">
            <!-- 构思结果卡片 -->
            <div v-if="ideaResult" class="idea-card">
              <div class="idea-title">{{ ideaResult.title||'未命名' }}</div>
              <div class="idea-genre" v-if="ideaResult.genre">{{ ideaResult.genre }}</div>
              <div class="idea-premise" v-if="ideaResult.premise">{{ ideaResult.premise }}</div>
              <div class="idea-hook" v-if="ideaResult.hook">💬 {{ ideaResult.hook }}</div>
              <div class="idea-wb" v-if="ideaResult.world_building">
                <div class="idea-sec-title">🌍 世界观</div>
                <div class="idea-wb-text">{{ ideaResult.world_building }}</div>
              </div>
              <div class="idea-chars" v-if="ideaResult.characters?.length">
                <div class="idea-sec-title">👥 角色 ({{ ideaResult.characters.length }})</div>
                <div v-for="c in ideaResult.characters" :key="c.name" class="idea-char">
                  <span class="ic-name">{{ c.name }}</span>
                  <span class="ic-role">{{ c.role }}</span>
                  <div class="ic-traits" v-if="c.traits">{{ c.traits }}</div>
                  <div class="ic-meta">
                    <span v-if="c.desire">💭 {{ c.desire }}</span>
                    <span v-if="c.fear"> · 😨 {{ c.fear }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 大纲完成提示 -->
            <div v-if="outlineResult" class="outline-done">
              <b>📋 大纲生成完成！</b> 左侧目录已更新，切换到「写作」模式开始创作。
            </div>

            <!-- 审稿结果 -->
            <div v-if="reviewResult" class="review-card">
              <div class="text">{{ reviewResult }}</div>
            </div>

            <div v-if="!ideaResult&&!stream&&!txt&&sel" class="emp">
              <div class="emp-icon">✍️</div>
              <div>本节尚未写作</div>
              <div class="emp-sub">点击下方「执行」或「自动续写」开始</div>
            </div>
            <div v-else-if="!ideaResult&&!stream&&!txt" class="emp">
              <div class="emp-icon">📖</div>
              <div>选择左侧目录中的一节</div>
              <div class="emp-sub">点击即可查看或续写</div>
            </div>
            <div v-if="!ideaResult" class="text">{{ stream||txt }}</div>
            <span v-if="busy" class="cur">▌</span>
          </template>

          <!-- 全文 -->
          <div v-if="tab==='f'">
            <div v-if="fulltextLoading" class="emp">
              <div class="ld-spinner" style="margin:0 auto 12px"></div>
              <div>加载全文中...</div>
            </div>
            <div v-else-if="fulltext" class="text">{{ fulltext }}</div>
            <div v-else class="emp">
              <div class="emp-icon">📚</div>
              <div>暂无内容</div>
            </div>
          </div>

          <!-- 角色 -->
          <div v-if="tab==='r'">
            <div v-if="!chars.length" class="emp">
              <div class="emp-icon">👥</div>
              <div>暂无角色</div>
              <div class="emp-sub">生成构思后自动创建</div>
            </div>
            <div v-for="c in chars" :key="c.id" class="chc" @click="toggleChar(c)">
              <div class="chc-hd">
                <b>{{ c.name }}</b>
                <span class="chcr">{{ c.role }}</span>
                <span class="chc-expand">{{ expandedChar===c.id?'▾':'▸' }}</span>
              </div>
              <div class="chct" v-if="c.traits">🎭 {{ c.traits }}</div>
              <div class="chct" v-if="c.desire">💭 {{ c.desire }}</div>
              <div class="chct" v-if="c.fear">😨 {{ c.fear }}</div>

              <!-- 展开详情 -->
              <div v-if="expandedChar===c.id" class="chc-detail">
                <!-- 关系网 -->
                <div class="chc-sec" v-if="charRelations[c.id]?.length">
                  <div class="chc-sec-title">🔗 关系网</div>
                  <div v-for="r in charRelations[c.id]" :key="r.with" class="chc-rel">
                    <span class="rel-other">{{ r.with }}</span>
                    <span class="rel-type">{{ r.type }}</span>
                    <span class="rel-desc">{{ r.description }}</span>
                  </div>
                </div>
                <div v-else-if="charRelations[c.id]" class="chc-sec">
                  <div class="chc-sec-title">🔗 关系网</div>
                  <div class="chct-dim">暂无关系记录</div>
                </div>

                <!-- 大事记 -->
                <div class="chc-sec" v-if="charTimeline[c.id]?.length">
                  <div class="chc-sec-title">📅 出场记录</div>
                  <div v-for="e in charTimeline[c.id]" :key="e.section" class="chc-event">
                    <span class="ev-loc">{{ e.volume }} › {{ e.chapter }}</span>
                    <span class="ev-sec">{{ e.section }}</span>
                    <span class="ev-sum" v-if="e.summary">{{ e.summary }}</span>
                  </div>
                </div>

                <!-- 备注 -->
                <div class="chc-sec">
                  <div class="chc-sec-title">📝 备注</div>
                  <textarea v-model="c._notesDraft" placeholder="添加角色备注、弧光计划、关系变化..." rows="3"
                    class="chc-notes-input"></textarea>
                  <button class="b1 b-sm" @click.stop="saveCharNotes(c)" :disabled="c._saving">
                    {{ c._saving?'保存中...':'保存备注' }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 世界观 -->
          <div v-if="tab==='w'">
            <div v-if="wb" class="text wb-text">{{ wb }}</div>
            <div v-else class="emp">
              <div class="emp-icon">🌍</div>
              <div>暂无世界观设定</div>
              <div class="emp-sub">生成构思后自动创建</div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <SettingsModal v-if="showSettings" @close="showSettings=false" />

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="msg" class="toast" @click="msg=''">{{ msg }}</div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SettingsModal from '../components/SettingsModal.vue'
import { useSettings } from '../stores/settings.js'

const route=useRoute(),router=useRouter(),{settings}=useSettings()
const nid=ref(route.params.id),loading=ref(true),err=ref(''),mode=ref('idea'),tab=ref('c'),busy=ref(false),msg=ref('')
const novel=ref(null),ideaText=ref(''),vols=ref(3),chaps=ref(4),outline=ref([]),sel=ref(null)
const txt=ref(''),stream=ref(''),fb=ref(''),chars=ref([]),wb=ref('')
const progress=ref({done:0,total:0,words:0}),cz=ref(null),showSettings=ref(false)
const sbW=ref(220),ctW=ref(340)
const autoWriting=ref(false),autoIdx=ref(0),autoTotal=ref(0),autoDone=ref(0)
const autoCurTitle=ref(''),autoDoneWords=ref(0),autoLastAnalysis=ref(''),autoNodeId=ref(null)
const fulltext=ref(''),fulltextLoading=ref(false)
const expandedChar=ref(null),charRelations=ref({}),charTimeline=ref({})
const ideaResult=ref(null)
const generating=ref(''),outlineResult=ref(null),reviewResult=ref(null)

const modes=[{k:'idea',i:'💡',l:'构思'},{k:'outline',i:'📋',l:'大纲'},{k:'write',i:'✍️',l:'写作'},{k:'review',i:'🔍',l:'审稿'}]
const nodeCount=computed(()=>{let n=0;outline.value.forEach(v=>v.chapters?.forEach(c=>n+=c.sections?.length||0));return n})
const progPct=computed(()=>progress.value.total?Math.round(progress.value.done/progress.value.total*100):0)
const progDone=computed(()=>progress.value.done),progTotal=computed(()=>progress.value.total),progWords=computed(()=>progress.value.words)

const api=async(u,o={})=>{const r=await fetch(u,{headers:{'Content-Type':'application/json'},...o});if(!r.ok)throw new Error((await r.text()).slice(0,200));return r.json()}

async function loadOutline(){try{outline.value=(await api('/api/novels/'+nid.value+'/outline')).tree||[]}catch{}}

onMounted(async()=>{
  try{
    const d=await api('/api/novels/'+nid.value)
    novel.value=d.novel;chars.value=d.characters||[];wb.value=d.world_building||''
    progress.value=d.progress||{done:0,total:0,words:0}
    await loadOutline()
  }catch(e){err.value=e.message}
  loading.value=false
})

async function doIdea(){
  if(!ideaText.value)return;busy.value=true;stream.value='';tab.value='c';msg.value=''
  try{
    const r=await fetch('/api/novels/'+nid.value+'/idea',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idea:ideaText.value})})
    const rd=r.body.getReader(),dc=new TextDecoder();let b='',f=''
    while(true){
      const{done,value}=await rd.read();if(done)break
      b+=dc.decode(value,{stream:true});const ls=b.split('\n\n');b=ls.pop()
      for(const l of ls){
        if(!l.startsWith('data: '))continue
        try{const d=JSON.parse(l.slice(6))
          if(d.type==='chunk'){f+=d.text;stream.value=f}
          else if(d.type==='done'){
            novel.value={...novel.value,title:d.data.title,genre:d.data.genre}
            chars.value=d.data.characters||[];wb.value=d.data.world_building||''
            ideaResult.value=d.data;txt.value='';stream.value=''
          }
        }catch{}
      }
    }
  }catch(e){msg.value='构思失败: '+e.message}
  busy.value=false
}

async function doOutline(){
  busy.value=true;stream.value='';tab.value='c';msg.value='';generating.value='outline'
  try{
    const r=await fetch('/api/novels/'+nid.value+'/outline',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({volumes:vols.value,chapters_per_vol:chaps.value})})
    const rd=r.body.getReader(),dc=new TextDecoder();let b='',f=''
    while(true){
      const{done,value}=await rd.read();if(done)break
      b+=dc.decode(value,{stream:true});const ls=b.split('\n\n');b=ls.pop()
      for(const l of ls){
        if(!l.startsWith('data: '))continue
        try{const d=JSON.parse(l.slice(6))
          if(d.type==='chunk'){f+=d.text;stream.value=f}
          else if(d.type==='done'){await loadOutline();outlineResult.value=true;txt.value='';stream.value=''}
        }catch{}
      }
    }
  }catch(e){msg.value='大纲失败: '+e.message}
  busy.value=false;generating.value=''
}

async function pick(id){
  sel.value=id;mode.value='write';tab.value='c';autoWriting.value=false;ideaResult.value=null
  try{const d=await api('/api/novels/'+nid.value+'/sections/'+id);txt.value=d.content||'';stream.value=''}catch(e){txt.value='';msg.value='加载内容失败: '+e.message}
}

async function doWrite(){
  if(!sel.value)return;busy.value=true;stream.value='';txt.value='';tab.value='c';msg.value=''
  try{
    const r=await fetch('/api/novels/'+nid.value+'/write/'+sel.value,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({feedback:fb.value})})
    const rd=r.body.getReader(),dc=new TextDecoder();let b='',f=''
    while(true){
      const{done,value}=await rd.read();if(done)break
      b+=dc.decode(value,{stream:true});const ls=b.split('\n\n');b=ls.pop()
      for(const l of ls){
        if(!l.startsWith('data: '))continue
        try{const d=JSON.parse(l.slice(6))
          if(d.type==='chunk'){f+=d.text;stream.value=f}
          else if(d.type==='done'){txt.value=d.content||f;fb.value='';await loadOutline();try{const nd=await api('/api/novels/'+nid.value);progress.value=nd.progress||progress.value}catch{}}
        }catch{}
      }
    }
  }catch(e){msg.value='写作失败: '+e.message}
  busy.value=false
}

async function doReview(){
  busy.value=true;stream.value='';tab.value='c';msg.value='';generating.value='review'
  try{
    const r=await fetch('/api/novels/'+nid.value+'/review',{method:'POST'})
    const rd=r.body.getReader(),dc=new TextDecoder();let b='',f=''
    while(true){
      const{done,value}=await rd.read();if(done)break
      b+=dc.decode(value,{stream:true});const ls=b.split('\n\n');b=ls.pop()
      for(const l of ls){
        if(!l.startsWith('data: '))continue
        try{const d=JSON.parse(l.slice(6))
          if(d.type==='chunk'){f+=d.text;stream.value=f}
          else if(d.type==='done'){reviewResult.value=d.content||f;txt.value='';stream.value=''}
        }catch{}
      }
    }
  }catch(e){msg.value='审稿失败: '+e.message}
  busy.value=false;generating.value=''
}

function exportNovel(){window.open('/api/novels/'+nid.value+'/export?format=txt')}

async function loadFulltext(){
  if(fulltext.value)return
  fulltextLoading.value=true
  try{const d=await api('/api/novels/'+nid.value+'/fulltext');fulltext.value=d.text||''}catch(e){msg.value='加载全文失败'}
  fulltextLoading.value=false
}

async function toggleChar(c){
  if(expandedChar.value===c.id){expandedChar.value=null;return}
  expandedChar.value=c.id
  if(!c._notesDraft&&c._notesDraft!=='')c._notesDraft=c.notes||''
  if(!charRelations.value[c.id]){
    try{
      const d=await api('/api/novels/'+nid.value+'/characters/'+c.id)
      charRelations.value[c.id]=d.relationships||[]
      charTimeline.value[c.id]=d.timeline||[]
    }catch{charRelations.value[c.id]=[];charTimeline.value[c.id]=[]}
  }
}

async function saveCharNotes(c){
  c._saving=true
  try{await fetch('/api/novels/'+nid.value+'/characters/'+c.id+'/notes',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:c._notesDraft||''})});c.notes=c._notesDraft;msg.value='备注已保存'}catch(e){msg.value='保存失败'}
  c._saving=false
}

async function doAutoWrite(){
  busy.value=true;stream.value='';tab.value='c';msg.value='';autoWriting.value=true
  autoDone.value=0;autoDoneWords.value=0;autoLastAnalysis.value=''
  try{
    const r=await fetch('/api/novels/'+nid.value+'/auto-write',{method:'POST'})
    const rd=r.body.getReader(),dc=new TextDecoder();let b=''
    while(true){const{done,value}=await rd.read();if(done)break;b+=dc.decode(value,{stream:true});const ls=b.split('\n\n');b=ls.pop()
      for(const l of ls){if(!l.startsWith('data: '))continue;try{const d=JSON.parse(l.slice(6))
        if(d.type==='chunk'){stream.value=(stream.value||'')+d.text}
        else if(d.type==='auto_start'){autoTotal.value=d.total;autoIdx.value=1;stream.value=''}
        else if(d.type==='section_start'){
          autoIdx.value=d.index;autoTotal.value=d.total;autoCurTitle.value=d.title
          autoNodeId.value=d.node_id;stream.value=''
        }
        else if(d.type==='section_done'){
          autoDone.value=d.index;autoDoneWords.value+=d.words||0
          autoNodeId.value=null;stream.value=''
          await loadOutline()
          try{const nd=await api('/api/novels/'+nid.value);progress.value=nd.progress||progress.value}catch{}
        }
        else if(d.type==='analyzing'){autoLastAnalysis.value='🔍 分析中...'}
        else if(d.type==='analysis_done'){
          let parts=[]
          if(d.new_chars)parts.push(`+${d.new_chars}角色`)
          if(d.new_threads)parts.push(`+${d.new_threads}伏笔`)
          autoLastAnalysis.value=parts.length?'📊 '+parts.join(' · '):'✓ 分析完成'
        }
        else if(d.type==='auto_done'){autoLastAnalysis.value='✅ '+d.message;msg.value=d.message}
        else if(d.type==='error'){msg.value='续写失败: '+d.message}
      }catch{}}
    }
    setTimeout(()=>{autoWriting.value=false},3000)
  }catch(e){msg.value='自动续写出错: '+e.message;autoWriting.value=false}
  busy.value=false
}

// 拖拽
let drag=null,ds=0,do2=0
function startDrag(p,e){drag=p;ds=e.clientX;do2=p==='sb'?sbW.value:ctW.value;document.addEventListener('mousemove',onDrag);document.addEventListener('mouseup',stopDrag)}
function onDrag(e){if(!drag)return;const d=e.clientX-ds;if(drag==='sb')sbW.value=Math.max(160,Math.min(360,do2+d));else ctW.value=Math.max(240,Math.min(500,do2+d))}
function stopDrag(){drag=null;document.removeEventListener('mousemove',onDrag);document.removeEventListener('mouseup',stopDrag)}

watch(stream,()=>nextTick(()=>{if(cz.value)cz.value.scrollTop=cz.value.scrollHeight}))
watch(msg,v=>{if(v)setTimeout(()=>msg.value='',4000)})
const statPulse=ref({words:false,chars:false,prog:false})
watch(progWords,(n,o)=>{if(n!==o){statPulse.value.words=true;setTimeout(()=>statPulse.value.words=false,600)}})
watch(()=>chars.value.length,(n,o)=>{if(n!==o){statPulse.value.chars=true;setTimeout(()=>statPulse.value.chars=false,600)}})
watch(progDone,(n,o)=>{if(n!==o){statPulse.value.prog=true;setTimeout(()=>statPulse.value.prog=false,600)}})
</script>

<style scoped>
/* ═══════════════════════ Layout ═══════════════════════ */
.ws{display:flex;height:100vh;position:relative;z-index:1}
.ld{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;width:100%;gap:12px;color:var(--text3)}
.ld-spinner{width:32px;height:32px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.ld-text{font-size:14px;color:var(--text2)}
.err-icon{width:48px;height:48px;border-radius:50%;background:rgba(251,113,133,.15);color:#fb7185;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700}
.err-msg{font-size:14px;color:var(--red);max-width:320px;text-align:center;line-height:1.6}
.btn-back{padding:8px 20px;border:1px solid var(--border);border-radius:10px;background:transparent;color:var(--text2);font-size:13px;cursor:pointer;margin-top:8px}
.btn-back:hover{background:var(--surface2);color:var(--text)}

/* ═══════════════════════ Sidebar ═══════════════════════ */
.sb{min-width:160px;background:linear-gradient(180deg,#13132a 0%,#0d0d1f 100%);border-right:1px solid var(--border);display:flex;flex-direction:column;padding:0;position:relative}
.sb::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#6366f1,var(--accent),var(--accent2));z-index:2}
.sb-top{padding:18px 14px 12px}
.back{font-size:11px;color:var(--text3);cursor:pointer;padding:2px 6px;border-radius:4px;display:inline-block;margin-bottom:6px;transition:.15s}
.back:hover{background:rgba(255,255,255,.05);color:var(--text)}
.name{font-size:13px;font-weight:700;color:var(--text);margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.genre{font-size:10px;color:var(--text3)}

.nav{display:flex;flex-direction:column;gap:2px;padding:0 8px;margin-bottom:10px}
.nb{display:flex;align-items:center;gap:6px;padding:9px 12px;border:none;border-radius:10px;background:transparent;color:var(--text2);font-size:12px;text-align:left;cursor:pointer;transition:.15s;position:relative}
.nb:hover{background:rgba(255,255,255,.04);color:var(--text);transform:translateX(3px)}
.nb.on{background:var(--accent-dim);color:var(--accent);font-weight:600;box-shadow:inset 0 0 0 1px rgba(139,140,248,.2)}
.nb-i{font-size:14px;line-height:1}
.nb-l{flex:1}
.nb-hint{font-size:10px;color:var(--accent);background:rgba(139,140,248,.12);padding:2px 8px;border-radius:8px;min-width:40px;text-align:center;font-weight:600}

/* Stats — staggered entrance */
.stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;padding:0 14px;margin-bottom:12px}
.stat{background:rgba(19,19,42,.8);border:1px solid var(--border);border-radius:12px;padding:10px 6px;text-align:center;transition:.2s;cursor:default;position:relative;overflow:hidden;animation:card-in .5s ease backwards}
.stat:nth-child(1){animation-delay:.05s}
.stat:nth-child(2){animation-delay:.12s}
.stat:nth-child(3){animation-delay:.19s}
.stat::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.stat:nth-child(1)::before{background:linear-gradient(90deg,#818cf8,#6366f1)}
.stat:nth-child(2)::before{background:linear-gradient(90deg,#6ee7b7,#34d399)}
.stat:nth-child(3)::before{background:linear-gradient(90deg,#fbbf24,#f59e0b)}
.stat:hover{transform:translateY(-3px);box-shadow:0 8px 25px rgba(0,0,0,.4);border-color:rgba(255,255,255,.1)}
@keyframes card-in{from{opacity:0;transform:translateY(12px) scale(.95)}to{opacity:1;transform:translateY(0) scale(1)}}
.stat.pulse{animation:num-glow .6s ease}
.stat.pulse .st-n{animation:num-pop .4s ease}
@keyframes num-glow{0%,100%{box-shadow:0 0 0 rgba(139,140,248,0)}50%{box-shadow:0 0 20px rgba(139,140,248,.4),inset 0 0 0 1px rgba(139,140,248,.3)}}
@keyframes num-pop{0%{transform:scale(1)}50%{transform:scale(1.15);color:var(--accent)}100%{transform:scale(1)}}
.st-n{display:block;font-size:15px;font-weight:800;color:var(--text);margin-bottom:2px}
.st-l{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}

.panel{flex:1;overflow-y:auto;padding:0 14px 10px}
.pm{display:flex;flex-direction:column;gap:6px}
.panel textarea{width:100%;padding:10px;border:1px solid var(--border);border-radius:10px;font-size:12px;resize:vertical;outline:none;font-family:inherit;background:rgba(0,0,0,.25);color:var(--text);line-height:1.6;transition:.15s}
.panel textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(139,140,248,.1)}
.kv{display:flex;align-items:center;justify-content:space-between;font-size:12px;color:var(--text2)}
.kv input{width:52px;padding:5px 8px;border:1px solid var(--border);border-radius:8px;text-align:center;outline:none;background:rgba(0,0,0,.25);color:var(--text);font-size:12px}
.kv input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(139,140,248,.1)}
.review-hint{font-size:11px;color:var(--text3);line-height:1.6;margin-bottom:2px}

/* Progress */
.pg-wrap{background:rgba(19,19,42,.8);border:1px solid var(--border);border-radius:12px;padding:12px 14px;margin-bottom:4px}
.pg{height:6px;background:var(--border);border-radius:3px;overflow:hidden;margin-bottom:8px}
.pgf{height:100%;background:linear-gradient(90deg,#6366f1,var(--accent),var(--accent2),#c084fc);border-radius:3px;transition:width .8s ease;box-shadow:0 0 12px rgba(139,140,248,.4);position:relative;overflow:hidden}
.pgf::before{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.15),transparent);animation:shimmer 2s ease-in-out infinite}
.pgf::after{content:'';position:absolute;right:0;top:-2px;width:10px;height:10px;border-radius:50%;background:#c084fc;box-shadow:0 0 8px rgba(192,132,252,.6)}
@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.pgt{font-size:10px;color:var(--text3)}

/* Buttons */
.b1{width:100%;padding:11px;border:none;border-radius:12px;background:linear-gradient(135deg,var(--accent),#6366f1);color:#fff;font-size:13px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;transition:.2s;box-shadow:0 4px 15px rgba(99,102,241,.3)}
.b1:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 8px 25px rgba(99,102,241,.45)}
.b1:disabled{opacity:.35;cursor:default;transform:none;box-shadow:none}
.b-auto{background:linear-gradient(135deg,#6366f1,#a78bfa,#c084fc);background-size:200% 200%;animation:auto-glow 3s ease infinite;box-shadow:0 4px 20px rgba(167,139,250,.35)}
@keyframes auto-glow{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
.b-auto:hover:not(:disabled){box-shadow:0 8px 30px rgba(167,139,250,.55)}
.sp{width:16px;height:16px;border:2px solid rgba(255,255,255,.25);border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite}

.foot{padding:10px 14px;border-top:1px solid var(--border);margin-top:auto;display:flex;gap:6px}
.b2{flex:1;padding:9px 6px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--text2);font-size:11px;cursor:pointer;text-align:center;transition:.15s}
.b2:hover{background:rgba(255,255,255,.04);color:var(--text);border-color:rgba(255,255,255,.1)}

/* ═══════════════════════ Grip ═══════════════════════ */
.grip{width:5px;cursor:col-resize;background:transparent;transition:background .2s;flex-shrink:0;position:relative;z-index:10}
.grip:hover,.grip:active{background:var(--accent)}
.grip::after{content:'';position:absolute;inset:-4px 0}

/* ═══════════════════════ TOC ═══════════════════════ */
.ct{width:340px;min-width:260px;max-width:440px;display:flex;flex-direction:column;background:var(--bg);position:relative}
.ct::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,var(--accent),transparent);opacity:.12;z-index:1}
.cth{padding:12px 16px;font-size:12px;font-weight:600;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;color:var(--text2)}
.ctn{font-size:10px;background:var(--surface2);color:var(--text3);padding:2px 8px;border-radius:8px}
.ctb{flex:1;overflow-y:auto;padding:4px 0}

.toc-vol{margin-bottom:2px}
.tv{font-size:12px;font-weight:600;color:var(--text);padding:6px 14px 2px;cursor:pointer;user-select:none;display:flex;align-items:center;gap:4px}
.tv:hover{color:var(--accent)}
.tv-arrow{font-size:10px;color:var(--text3);width:12px}
.tc{font-size:11px;color:var(--text2);padding:2px 26px;font-weight:500}

.ts{display:flex;align-items:center;gap:6px;padding:3px 28px 3px 34px;font-size:11px;color:var(--text3);cursor:pointer;border-radius:4px;transition:.1s;margin:0 8px}
.ts:hover{background:var(--surface2);color:var(--text2)}
.ts.sel{background:var(--accent-dim);color:var(--accent)}
.ts.done{color:var(--text)}
.ts.writing{background:rgba(99,102,241,.1);color:#818cf8}
.ts-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;background:var(--border)}
.ts-dot.done{background:var(--green)}
.ts-dot.pending{background:var(--border)}
.ts-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ts-wc{font-size:9px;color:var(--text3)}

.ctf{display:flex;gap:8px;padding:10px 14px;border-top:1px solid var(--border)}
.ctf input{flex:1;padding:8px 12px;border:1px solid var(--border);border-radius:10px;font-size:12px;outline:none;background:var(--surface);color:var(--text)}
.ctf input:focus{border-color:var(--accent)}
.b-exec{width:auto;padding:8px 16px;white-space:nowrap}

/* ═══════════════════════ Content ═══════════════════════ */
.rt{flex:1;min-width:300px;display:flex;flex-direction:column;background:var(--bg-glass);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border-left:1px solid var(--glass-border)}
.rtt{display:flex;border-bottom:1px solid var(--glass-border);padding:0 8px;background:rgba(0,0,0,.1)}
.rtb{flex:1;display:flex;align-items:center;justify-content:center;gap:5px;padding:11px 4px;border:none;background:transparent;color:var(--text3);font-size:11px;cursor:pointer;border-bottom:2px solid transparent;transition:var(--transition-fast)}
.rtb:hover{color:var(--text2)}
.rtb.on{color:var(--accent);border-bottom-color:var(--accent)}
.rtb-i{font-size:13px}
.rtc{flex:1;overflow-y:auto;padding:20px 24px}
.rtc::-webkit-scrollbar{width:4px}
.rtc::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}

/* Text */
.text{font-size:inherit;line-height:2;white-space:pre-wrap;max-width:720px;color:var(--text)}
.cur{animation:blink 1s step-end infinite;color:var(--accent);font-size:inherit}@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
.wb-text{color:var(--text2);font-style:italic}

/* Empty state */
.emp{text-align:center;padding:64px 0}
.emp-icon{font-size:36px;margin-bottom:12px;opacity:.6}
.emp{color:var(--text3);font-size:13px}
.emp-sub{font-size:11px;color:var(--text3);opacity:.6;margin-top:4px}

/* Character cards */
.chc{padding:14px;margin-bottom:8px;background:var(--bg-card);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-radius:var(--radius);border:1px solid var(--glass-border);transition:var(--transition-bounce);cursor:pointer}
.chc:hover{border-color:var(--border-glow);box-shadow:var(--shadow-card-hover);transform:translateY(-1px)}
.chc-hd{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.chc-hd b{font-size:14px;color:var(--text)}
.chcr{font-size:10px;padding:2px 8px;border-radius:6px;background:var(--accent-dim);color:var(--accent)}
.chc-expand{margin-left:auto;font-size:12px;color:var(--text3)}
.chct{font-size:11px;color:var(--text3);margin-top:3px;line-height:1.5}
.chct-dim{font-size:11px;color:var(--text3);opacity:.6;font-style:italic}

/* Character detail */
.chc-detail{margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}
.chc-sec{margin-bottom:14px}
.chc-sec-title{font-size:11px;font-weight:600;color:var(--text2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.4px}

/* Relationships */
.chc-rel{display:flex;align-items:center;gap:8px;padding:5px 8px;margin-bottom:3px;background:var(--bg);border-radius:6px;font-size:11px}
.rel-other{font-weight:550;color:var(--text);white-space:nowrap}
.rel-type{font-size:9px;padding:1px 6px;border-radius:4px;background:var(--accent-dim);color:var(--accent);white-space:nowrap}
.rel-desc{color:var(--text3);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* Events */
.chc-event{padding:4px 0;margin-bottom:2px;font-size:10px;border-left:2px solid var(--border);padding-left:8px}
.ev-loc{color:var(--text2);font-weight:500}
.ev-sec{color:var(--text3);margin-left:4px}
.ev-sum{display:block;color:var(--text3);margin-top:1px}

/* Notes */
.chc-notes-input{width:100%;padding:8px;border:1px solid var(--border);border-radius:8px;font-size:11px;resize:vertical;outline:none;font-family:inherit;background:var(--bg);color:var(--text);line-height:1.5;margin-top:4px}
.chc-notes-input:focus{border-color:var(--accent)}
.b-sm{width:auto;padding:6px 14px;font-size:11px;margin-top:6px}

/* ═══════════════════════ Loading Animation ═══════════════════════ */
.gen-overlay{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 20px;text-align:center}
.gen-spinner{width:40px;height:40px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;margin-bottom:16px}
.gen-text{font-size:15px;font-weight:550;color:var(--text);margin-bottom:6px}
.gen-sub{font-size:11px;color:var(--text3)}

/* ═══════════════════════ Outline Card ═══════════════════════ */
.outline-done{padding:12px 16px;margin-bottom:14px;background:rgba(110,231,183,.08);border:1px solid rgba(110,231,183,.2);border-radius:10px;font-size:13px;color:var(--green);text-align:center;max-width:720px}
.outline-done b{font-weight:650}

/* ═══════════════════════ Review Card ═══════════════════════ */
.review-card{max-width:720px}
.review-card .text{white-space:pre-wrap;line-height:1.8;font-size:.9em;color:var(--text2)}

/* ═══════════════════════ Idea Card ═══════════════════════ */
.idea-card{max-width:720px;animation:fade-in .3s ease}
.idea-title{font-size:1.6em;font-weight:700;color:var(--text);margin-bottom:4px}
.idea-genre{display:inline-block;font-size:11px;padding:3px 10px;border-radius:6px;background:var(--accent-dim);color:var(--accent);margin-bottom:14px}
.idea-premise{font-size:.95em;color:var(--text2);line-height:1.8;padding:12px 16px;background:var(--surface2);border-radius:10px;border-left:3px solid var(--accent);margin-bottom:14px;font-style:italic}
.idea-hook{font-size:.85em;color:var(--accent);margin-bottom:14px}
.idea-sec-title{font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:8px}
.idea-wb{margin-bottom:16px}
.idea-wb-text{font-size:.9em;color:var(--text2);line-height:1.7}
.idea-chars{margin-bottom:16px}
.idea-char{padding:10px 12px;margin-bottom:6px;background:var(--surface2);border-radius:10px;border:1px solid var(--border)}
.ic-name{font-size:.95em;font-weight:600;color:var(--text);margin-right:8px}
.ic-role{font-size:10px;padding:1px 6px;border-radius:4px;background:var(--accent-dim);color:var(--accent)}
.ic-traits{font-size:.8em;color:var(--text3);margin-top:4px}
.ic-meta{font-size:.75em;color:var(--text3);margin-top:3px}

/* ═══════════════════════ Auto-write Panel ═══════════════════════ */
.auto-panel{padding:8px 0}
.auto-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.auto-title{font-size:15px;font-weight:650;color:var(--text)}
.auto-progress{font-size:11px;background:var(--accent-dim);color:var(--accent);padding:3px 10px;border-radius:8px}
.auto-dots{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:16px}
.ad{width:8px;height:8px;border-radius:50%;background:var(--border);transition:.3s}
.ad.done{background:var(--green);box-shadow:0 0 6px rgba(110,231,183,.3)}
.ad.cur{background:var(--accent);box-shadow:0 0 8px rgba(129,140,248,.5);animation:pulse-dot 1s ease-in-out infinite}
@keyframes pulse-dot{0%,100%{transform:scale(1)}50%{transform:scale(1.6)}}
.auto-cur{font-size:12px;color:var(--text2);margin-bottom:8px;padding:8px 12px;background:var(--surface2);border-radius:8px;border-left:3px solid var(--accent)}
.auto-stats{display:flex;gap:16px;font-size:11px;color:var(--text3);margin-bottom:12px}
.auto-text{font-size:inherit;line-height:2;white-space:pre-wrap;color:var(--text2);max-width:720px}

/* ═══════════════════════ Toast ═══════════════════════ */
.toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);padding:10px 24px;background:var(--surface2);border:1px solid var(--border);border-radius:12px;color:var(--text);font-size:12px;z-index:999;box-shadow:0 8px 32px rgba(0,0,0,.3);cursor:pointer;white-space:nowrap}
.toast-enter-active{transition:all .3s ease}
.toast-leave-active{transition:all .2s ease}
.toast-enter-from{opacity:0;transform:translateX(-50%) translateY(-12px)}
.toast-leave-to{opacity:0;transform:translateX(-50%) translateY(-8px)}

/* ═══════════════════════ Transitions ═══════════════════════ */
.pm{animation:fade-in .2s ease}
@keyframes fade-in{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
</style>
