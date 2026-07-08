<template>
  <div class="root">
    <video class="bg-video" autoplay loop muted playsinline :key="settings.bgVideo">
      <source :src="'/videos/'+settings.bgVideo+'.mp4'" type="video/mp4" />
    </video>
    <div class="bg-overlay"></div>
    <AmbientBg />
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </div>
</template>

<script setup>
import AmbientBg from './components/AmbientBg.vue'
import { useSettings } from './stores/settings.js'
const { settings } = useSettings()
</script>

<style>
@import './styles/variables.css';
*{margin:0;padding:0;box-sizing:border-box}
html,body,#app{height:100%;overflow:hidden}
body{font-family:var(--font);background:#09090f;color:var(--text);-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}
.root{position:relative;height:100vh;overflow:hidden;background:transparent}

.bg-video{
  position:fixed;inset:0;z-index:0;pointer-events:none;
  width:100%;height:100%;object-fit:cover;
}
.bg-overlay{
  position:fixed;inset:0;z-index:0;pointer-events:none;
  background:rgba(9,9,15,.55);
}

.fade-enter-active,.fade-leave-active{transition:opacity .3s ease}
.fade-enter-from,.fade-leave-to{opacity:0}
</style>
