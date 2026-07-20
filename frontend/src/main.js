import { createApp } from 'vue'
import router from './router' // Importamos nuestro mapa de rutas
import App from './App.vue'

const app = createApp(App)
app.use(router) // Le enchufamos el router a Vue
app.mount('#app')