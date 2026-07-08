import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import NovelView from '../views/NovelView.vue'

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/novel/:id', name: 'novel', component: NovelView, props: true },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
