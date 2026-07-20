<script setup>
import { ref } from 'vue';
import axios from 'axios';
import { useRouter } from 'vue-router';

const router = useRouter();
const username = ref('');
const password = ref('');
const mensaje = ref('');

const iniciarSesion = async () => {
  try {
    const respuesta = await axios.post('/api/login', {
      username: username.value,
      password: password.value
    });
    
    // Guardamos el usuario y REDIRIGIMOS al Dashboard
    localStorage.setItem('user', respuesta.data.user);
    router.push('/dashboard');
    
  } catch (error) {
    mensaje.value = error.response?.data?.message || "Error al conectar con el servidor";
  }
};
</script>

<template>
  <div style="font-family: sans-serif; padding: 40px; max-width: 400px; margin: 10vh auto; background: #fff; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
    
    <h2 style="text-align: center; color: #333; margin-bottom: 30px;">⚙️ SISTEMA ROOT</h2>

    <input 
      v-model="username" 
      type="text"
      placeholder="Usuario" 
      style="display: block; margin-bottom: 15px; width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;" 
    />
    
    <input 
      v-model="password" 
      type="password" 
      placeholder="Contraseña" 
      @keyup.enter="iniciarSesion"
      style="display: block; margin-bottom: 20px; width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;" 
    />
    
    <button 
      @click="iniciarSesion" 
      style="width: 100%; padding: 12px; background: #0d6efd; color: white; border: none; border-radius: 4px; font-weight: bold; font-size: 16px; cursor: pointer;">
      Entrar
    </button>

    <div 
      v-if="mensaje" 
      style="margin-top: 20px; padding: 15px; border-radius: 4px; text-align: center; font-weight: bold; background-color: #f8d7da; color: #842029; border: 1px solid #f5c2c7;">
      {{ mensaje }}
    </div>
  </div>
</template>