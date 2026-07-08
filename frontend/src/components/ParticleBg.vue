<template>
  <canvas ref="canvas" class="stars"></canvas>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const canvas = ref(null)
let ctx, w, h, particles, animId

const props = defineProps({
  count: { type: Number, default: 80 },
  color: { type: String, default: '129,140,248' }, // accent RGB
})

function init() {
  ctx = canvas.value.getContext('2d')
  resize()
  window.addEventListener('resize', resize)

  particles = []
  for (let i = 0; i < props.count; i++) {
    particles.push({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - .5) * .3, vy: (Math.random() - .5) * .3,
      r: Math.random() * 2 + .5,
      opacity: Math.random() * .5 + .2,
      pulse: Math.random() * Math.PI * 2,
    })
  }
  animate()
}

function resize() {
  w = canvas.value.width = window.innerWidth
  h = canvas.value.height = window.innerHeight
}

function animate() {
  ctx.clearRect(0, 0, w, h)

  for (const p of particles) {
    // 移动
    p.x += p.vx; p.y += p.vy
    if (p.x < 0) p.x = w; if (p.x > w) p.x = 0
    if (p.y < 0) p.y = h; if (p.y > h) p.y = 0

    p.pulse += .02
    const alpha = p.opacity + Math.sin(p.pulse) * .15

    // 画粒子
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${props.color},${alpha})`
    ctx.fill()

    // 画光晕
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.r * 3, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${props.color},${alpha * .15})`
    ctx.fill()
  }

  // 连线（近的粒子之间）
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x
      const dy = particles[i].y - particles[j].y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 120) {
        ctx.beginPath()
        ctx.moveTo(particles[i].x, particles[i].y)
        ctx.lineTo(particles[j].x, particles[j].y)
        ctx.strokeStyle = `rgba(${props.color},${.04 * (1 - dist / 120)})`
        ctx.lineWidth = .5
        ctx.stroke()
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
.stars {
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
}
</style>
