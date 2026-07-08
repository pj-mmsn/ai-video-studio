<template>
  <canvas ref="c" class="ambient"></canvas>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const c = ref(null)
let ctx, w, h, layers, animId, mouseX = .5, mouseY = .5

const props = defineProps({ count: { type: Number, default: 40 } })

function init() {
  ctx = c.value.getContext('2d')
  resize(); window.addEventListener('resize', resize)
  window.addEventListener('mousemove', e => { mouseX = e.clientX / w; mouseY = e.clientY / h })

  const colors = [[139,140,248],[167,139,250],[110,231,183],[251,191,36],[244,114,182],[56,189,248]]
  layers = [
    { name: 'deep', speed: .15, count: 8,  size: [80,160], alpha: [.04,.10], orbs: [] },
    { name: 'mid',  speed: .4,  count: 18, size: [25,60],  alpha: [.10,.20], orbs: [] },
    { name: 'near', speed: .8,  count: 14, size: [4,10],   alpha: [.18,.35], orbs: [] },
  ]
  for (const L of layers) {
    for (let i = 0; i < L.count; i++) {
      L.orbs.push({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - .5) * L.speed, vy: (Math.random() - .5) * L.speed * .6,
        r: L.size[0] + Math.random() * (L.size[1] - L.size[0]),
        color: colors[i % colors.length],
        phase: Math.random() * Math.PI * 2,
        pulse: Math.random() * .01 + .003,
      })
    }
  }
  animate()
}

function resize() {
  const dpr = window.devicePixelRatio || 1
  c.value.width  = window.innerWidth * dpr
  c.value.height = window.innerHeight * dpr
  c.value.style.width  = window.innerWidth + 'px'
  c.value.style.height = window.innerHeight + 'px'
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  if (layers?.length) {
    const ow = w, oh = h; w = window.innerWidth; h = window.innerHeight
    for (const L of layers) for (const o of L.orbs) {
      if (o.x > w) o.x = Math.random() * w
      if (o.y > h) o.y = Math.random() * h
      o.vx *= w / Math.max(ow, 1); o.vy *= h / Math.max(oh, 1)
    }
  } else { w = window.innerWidth; h = window.innerHeight }
}

function animate() {
  ctx.clearRect(0, 0, w, h)
  const t = Date.now() * .001

  // Mouse parallax offset
  const mx = (mouseX - .5) * 30, my = (mouseY - .5) * 30

  for (const L of layers) {
    const depth = L.name === 'deep' ? 0 : L.name === 'mid' ? .3 : .6
    const ox = mx * depth, oy = my * depth

    for (const o of L.orbs) {
      o.x += o.vx + ox * .01; o.y += o.vy + oy * .01
      if (o.x < -o.r * 2) o.x = w + o.r * 2
      if (o.x > w + o.r * 2) o.x = -o.r * 2
      if (o.y < -o.r * 2) o.y = h + o.r * 2
      if (o.y > h + o.r * 2) o.y = -o.r * 2

      const pulse = Math.sin(t * o.pulse * 40 + o.phase) * .5 + .5
      const alpha = L.alpha[0] + pulse * (L.alpha[1] - L.alpha[0])

      // Radial glow
      const grd = ctx.createRadialGradient(o.x, o.y, 0, o.x, o.y, o.r * 8)
      grd.addColorStop(0, `rgba(${o.color},${alpha})`)
      grd.addColorStop(.6, `rgba(${o.color},${alpha * .15})`)
      grd.addColorStop(1, 'transparent')
      ctx.beginPath(); ctx.arc(o.x, o.y, o.r * 8, 0, Math.PI * 2)
      ctx.fillStyle = grd; ctx.fill()

      // Core dot (only near layer)
      if (L.name === 'near') {
        ctx.beginPath(); ctx.arc(o.x, o.y, o.r * .3, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${o.color},${alpha + .15})`; ctx.fill()
      }
    }
  }

  // Inter-layer connections (near only)
  const near = layers[2].orbs
  for (let i = 0; i < near.length; i++) {
    for (let j = i + 1; j < near.length; j++) {
      const dx = near[i].x - near[j].x, dy = near[i].y - near[j].y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 180) {
        ctx.beginPath(); ctx.moveTo(near[i].x, near[i].y); ctx.lineTo(near[j].x, near[j].y)
        ctx.strokeStyle = `rgba(${near[i].color},${.03 * (1 - dist / 180)})`
        ctx.lineWidth = .4; ctx.stroke()
      }
    }
  }

  animId = requestAnimationFrame(animate)
}

onMounted(init)
onBeforeUnmount(() => {
  cancelAnimationFrame(animId)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
.ambient { position: fixed; inset: 0; z-index: 0; pointer-events: none; opacity: 1 }
</style>
