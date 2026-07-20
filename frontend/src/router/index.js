import { createRouter, createWebHistory } from 'vue-router';
import Login from '../views/Login.vue';
import Dashboard from '../views/Dashboard.vue';

const routes = [
  { path: '/', name: 'Login', component: Login },
  { 
    path: '/dashboard', 
    name: 'Dashboard', 
    component: Dashboard,
    meta: { requiresAuth: true } // ⚠️ Le ponemos esta etiqueta para saber que es privada
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

// ⚠️ EL GUARDIA DE SEGURIDAD (Navigation Guard)
router.beforeEach((to, from, next) => {
  // Buscamos si hay un usuario guardado en el navegador
  const isAuthenticated = localStorage.getItem('user');

  // Si la ruta a la que quiere ir es privada Y NO está logueado...
  if (to.meta.requiresAuth && !isAuthenticated) {
    next('/'); // Lo devolvemos a la fuerza al Login
  } else {
    next(); // Si todo está bien, lo dejamos pasar
  }
});

export default router;