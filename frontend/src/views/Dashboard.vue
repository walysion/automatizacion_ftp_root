<script setup>
import { ref, onMounted } from 'vue'; 
import axios from 'axios';
import { useRouter } from 'vue-router';

const router = useRouter();
const usuarioActual = ref(localStorage.getItem('user') || 'Administrador');

const cerrarSesion = async () => {
    try {
        await axios.post('/api/logout');
        localStorage.removeItem('user');
        router.push('/'); 
    } catch (error) {
        console.error("Error al cerrar sesión", error);
    }
};

// ==========================================
// LÓGICA DEL ROBOT ETL
// ==========================================
const ejecutando = ref(false);
const resultadoMensaje = ref('');
const resultadoTipo = ref('');

const ejecutarRobot = async () => {
    ejecutando.value = true;
    resultadoMensaje.value = '';
    
    try {
        const respuesta = await axios.post('/api/ejecutar-etl');
        resultadoTipo.value = 'success';
        resultadoMensaje.value = respuesta.data.message;
    } catch (error) {
        resultadoTipo.value = 'error';
        resultadoMensaje.value = error.response?.data?.message || 'Error fatal al comunicarse con el motor ETL.';
    } finally {
        ejecutando.value = false;
    }
};

// ==========================================
// LÓGICA DEL CONSTRUCTOR DE LAYOUT MULTIMANDANTE
// ==========================================
const mandanteActivo = ref('hites'); // Mandante por defecto
const columnasLayout = ref([]);
const nuevaColumnaNombre = ref('');
const nuevaColumnaTipo = ref('Texto');
const guardandoLayout = ref(false);
const mensajeLayout = ref('');

// Función para ir a buscar las columnas del mandante seleccionado a la base de datos
const cargarLayoutDelMandante = async () => {
    mensajeLayout.value = ''; // Limpiamos alertas
    try {
        const respuesta = await axios.get(`/api/layout/${mandanteActivo.value}`);
        if (respuesta.data.success && respuesta.data.columnas) {
            columnasLayout.value = respuesta.data.columnas;
            console.log(`Layout de ${mandanteActivo.value} cargado correctamente.`);
        }
    } catch (error) {
        console.error("Error al cargar el layout:", error);
    }
};

// Carga el layout inicial (Hites) apenas se abre la pantalla
onMounted(() => {
    cargarLayoutDelMandante();
});

// Añade una fila temporal en la tabla
const agregarColumna = () => {
    if (nuevaColumnaNombre.value.trim() === '') return;
    
    columnasLayout.value.push({
        id: Date.now(), 
        nombre: nuevaColumnaNombre.value.toUpperCase().replace(/ /g, '_'), 
        tipo: nuevaColumnaTipo.value
    });
    
    nuevaColumnaNombre.value = '';
    nuevaColumnaTipo.value = 'Texto';
};

// Elimina una fila temporal de la tabla
const eliminarColumna = (id) => {
    columnasLayout.value = columnasLayout.value.filter(col => col.id !== id);
};

// Envía la estructura final a PostgreSQL usando el mandante activo en la URL
const guardarLayout = async () => {
    guardandoLayout.value = true;
    mensajeLayout.value = '';
    
    try {
        await axios.post(`/api/layout/${mandanteActivo.value}/guardar`, {
            columnas: columnasLayout.value
        });
        mensajeLayout.value = `✅ Layout para ${mandanteActivo.value.toUpperCase()} guardado en PostgreSQL.`;
    } catch (error) {
        mensajeLayout.value = '❌ Error al guardar en la base de datos';
    } finally {
        guardandoLayout.value = false;
        setTimeout(() => { mensajeLayout.value = '' }, 4000);
    }
};
</script>

<template>
  <div style="font-family: sans-serif; padding: 20px; background-color: #e9ecef; min-height: 100vh; box-sizing: border-box;">
    
    <!-- Barra de navegación -->
    <nav style="background: #212529; color: white; padding: 15px 25px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h3 style="margin: 0;">⚙️ SISTEMA ROOT - Panel de Control</h3>
        <div>
            <span style="margin-right: 20px; font-weight: bold;">👋 Hola, {{ usuarioActual }}</span>
            <button @click="cerrarSesion" style="background: #dc3545; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; font-weight: bold;">Cerrar Sesión</button>
        </div>
    </nav>

    <!-- Contenedor Principal (Grid para las dos secciones) -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px;">
        
        <!-- TARJETA 1: ACCIONES DEL ROBOT -->
        <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); align-self: start;">
            <h3 style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px;">🤖 Operaciones del Motor ETL</h3>
            <p style="color: #6c757d; margin-bottom: 25px;">
                Dispara el Script de Selenium correspondiente para navegar de forma automatizada, descargar las carteras de clientes y procesar la información.
            </p>
            
            <button 
                @click="ejecutarRobot" 
                :disabled="ejecutando"
                style="padding: 14px 24px; color: white; border: none; border-radius: 6px; font-weight: bold; width: 100%; cursor: pointer;"
                :style="{ backgroundColor: ejecutando ? '#6c757d' : '#0d6efd' }"
            >
                <span v-if="ejecutando">⏳ Ejecutando Extracción Hites...</span>
                <span v-else>▶️ INICIAR ROBOT HITES</span>
            </button>

            <div v-if="resultadoMensaje" style="margin-top: 20px; padding: 15px; border-radius: 6px; font-weight: bold; text-align: center;"
                :style="{ backgroundColor: resultadoTipo === 'success' ? '#d1e7dd' : '#f8d7da', color: resultadoTipo === 'success' ? '#0f5132' : '#842029' }">
                {{ resultadoMensaje }}
            </div>
        </div>

        <!-- TARJETA 2: CONSTRUCTOR MULTIMANDANTE -->
        <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
            <h3 style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px;">📝 Mapeador de Layouts Multimandante</h3>
            
            <!-- CAJA INSTRUCTIVA -->
            <div style="background: #e2f0fe; color: #0a4275; padding: 15px; border-radius: 6px; margin-bottom: 20px; font-size: 14px; line-height: 1.4; border: 1px solid #b8dbfd;">
                💡 <strong>¿Qué hace esta pantalla?</strong><br>
                Cada portal (Hites, Ripley, etc.) entrega los archivos con nombres de columnas distintos. Aquí defines qué columnas y tipos de datos tiene el archivo de cada mandante. El motor ETL leerá esta configuración para inyectar la información correctamente en PostgreSQL.
            </div>

            <!-- SELECTOR DE MANDANTE ACTIVO -->
            <div style="margin-bottom: 20px; background: #f8f9fa; padding: 15px; border-radius: 6px; border: 1px solid #dee2e6;">
                <label style="font-weight: bold; color: #495057; display: block; margin-bottom: 8px;">🏢 Seleccionar Mandante a Configurar:</label>
                <select 
                    v-model="mandanteActivo" 
                    @change="cargarLayoutDelMandante"
                    style="width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 4px; font-size: 15px; font-weight: bold; background-color: white; cursor: pointer;"
                >
                    <option value="hites">Hites (Cartera Retail)</option>
                    <option value="ripley">Ripley (Cobranza Activa)</option>
                    <option value="lider">Líder / BCI (Prendario)</option>
                </select>
            </div>

            <!-- Controles para agregar nueva columna -->
            <div style="display: flex; gap: 10px; margin-bottom: 20px;">
                <input 
                    v-model="nuevaColumnaNombre" 
                    placeholder="Nombre de columna (Ej: RUT_DEUDOR)" 
                    @keyup.enter="agregarColumna"
                    style="flex: 2; padding: 10px; border: 1px solid #ccc; border-radius: 4px;"
                />
                <select v-model="nuevaColumnaTipo" style="flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 4px; background: white;">
                    <option value="Texto">Texto</option>
                    <option value="Numero">Número</option>
                    <option value="Fecha">Fecha</option>
                    <option value="Decimal">Decimal</option>
                </select>
                <button @click="agregarColumna" style="background: #198754; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; font-weight: bold;">+</button>
            </div>

            <!-- Tabla Reactiva de Columnas -->
            <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; overflow: hidden; margin-bottom: 20px;">
                <table style="width: 100%; border-collapse: collapse; text-align: left;">
                    <thead style="background: #e9ecef;">
                        <tr>
                            <th style="padding: 12px; border-bottom: 1px solid #dee2e6;">Nombre de Columna</th>
                            <th style="padding: 12px; border-bottom: 1px solid #dee2e6;">Tipo de Dato</th>
                            <th style="padding: 12px; border-bottom: 1px solid #dee2e6; text-align: center;">Acción</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="columna in columnasLayout" :key="columna.id">
                            <td style="padding: 12px; border-bottom: 1px solid #dee2e6; font-family: monospace; font-weight: bold;">{{ columna.nombre }}</td>
                            <td style="padding: 12px; border-bottom: 1px solid #dee2e6;">
                                <span style="background: #0dcaf0; color: #000; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: bold;">{{ columna.tipo }}</span>
                            </td>
                            <td style="padding: 12px; border-bottom: 1px solid #dee2e6; text-align: center;">
                                <button @click="eliminarColumna(columna.id)" style="background: #dc3545; color: white; border: none; border-radius: 4px; padding: 5px 10px; cursor: pointer;">X</button>
                            </td>
                        </tr>
                        <tr v-if="columnasLayout.length === 0">
                            <td colspan="3" style="padding: 20px; text-align: center; color: #6c757d; font-style: italic;">
                                No hay columnas para el mandante {{ mandanteActivo.toUpperCase() }}. Crea una arriba.
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Botón Guardar -->
            <button 
                @click="guardarLayout"
                :disabled="columnasLayout.length === 0 || guardandoLayout"
                style="width: 100%; padding: 12px; background: #ffc107; color: #000; border: none; border-radius: 4px; font-weight: bold; font-size: 16px; cursor: pointer;"
            >
                {{ guardandoLayout ? 'Guardando en BD...' : '💾 Guardar Configuración en PostgreSQL' }}
            </button>

            <!-- Mensaje de éxito/error -->
            <div v-if="mensajeLayout" style="margin-top: 15px; text-align: center; font-weight: bold; padding: 10px; background: #d1e7dd; color: #0f5132; border-radius: 4px;">
                {{ mensajeLayout }}
            </div>

        </div>

    </div>
  </div>
</template>