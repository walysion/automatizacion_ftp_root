<script setup>
import { ref, onMounted, computed } from 'vue'; 
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
// LÓGICA DEL CONSTRUCTOR Y CONFIGURACIÓN SFTP
// ==========================================
const mandanteActivo = ref('hites'); // Mandante por defecto
const columnasLayout = ref([]);
const configuracionSFTP = ref({
    dia: 'Martes',
    hora: '18:00',
    ruta: 'in/gestiones/mes_año'
});

const nuevaColumnaNombre = ref('');
const nuevaColumnaTipo = ref('Texto');
const guardandoLayout = ref(false);
const mensajeLayout = ref('');

// Función para ir a buscar las columnas y el SFTP a la base de datos
const cargarLayoutDelMandante = async () => {
    mensajeLayout.value = ''; // Limpiamos alertas
    try {
        const respuesta = await axios.get(`/api/layout/${mandanteActivo.value}`);
        if (respuesta.data.success) {
            columnasLayout.value = respuesta.data.columnas || [];
            configuracionSFTP.value = respuesta.data.sftp || { dia: 'Martes', hora: '18:00', ruta: '' };
        }
    } catch (error) {
        console.error("Error al cargar configuración:", error);
    }
};

// Carga el layout inicial apenas se abre la pantalla
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

// Envía la estructura final y configuración SFTP a PostgreSQL
const guardarLayout = async () => {
    guardandoLayout.value = true;
    mensajeLayout.value = '';
    
    try {
        await axios.post(`/api/layout/${mandanteActivo.value}/guardar`, {
            columnas: columnasLayout.value,
            sftp: configuracionSFTP.value
        });
        mensajeLayout.value = `✅ Layout y SFTP guardados para ${mandanteActivo.value.toUpperCase()}.`;
    } catch (error) {
        mensajeLayout.value = '❌ Error al guardar en la base de datos';
    } finally {
        guardandoLayout.value = false;
        setTimeout(() => { mensajeLayout.value = '' }, 4000);
    }
};

// ==========================================
// 🌟 PREVISUALIZADOR EXCEL (DATOS DE PRUEBA)
// ==========================================
const filaEjemplo = computed(() => {
    const fila = {};
    columnasLayout.value.forEach(col => {
        if (col.tipo === 'Numero') fila[col.nombre] = '16873765';
        else if (col.tipo === 'Fecha') fila[col.nombre] = '12-06-2026';
        else if (col.tipo === 'Decimal') fila[col.nombre] = '99.90';
        else fila[col.nombre] = 'Dato_Ejemplo'; // Texto
    });
    return fila;
});
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
    <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 20px;">
        
        <!-- COLUMNA IZQUIERDA: ROBOT Y SFTP -->
        <div style="display: flex; flex-direction: column; gap: 20px;">
            
            <!-- TARJETA 1: ACCIONES DEL ROBOT -->
            <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                <h3 style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px;">🤖 Operaciones ETL</h3>
                <p style="color: #6c757d; margin-bottom: 25px; font-size: 14px;">
                    Dispara el Script de Selenium para descargar carteras y procesar la información.
                </p>
                
                <button 
                    @click="ejecutarRobot" 
                    :disabled="ejecutando"
                    style="padding: 14px 24px; color: white; border: none; border-radius: 6px; font-weight: bold; width: 100%; cursor: pointer;"
                    :style="{ backgroundColor: ejecutando ? '#6c757d' : '#0d6efd' }"
                >
                    <span v-if="ejecutando">⏳ Ejecutando Extracción...</span>
                    <span v-else>▶️ INICIAR ROBOT HITES</span>
                </button>

                <div v-if="resultadoMensaje" style="margin-top: 15px; padding: 10px; border-radius: 6px; font-weight: bold; text-align: center;"
                    :style="{ backgroundColor: resultadoTipo === 'success' ? '#d1e7dd' : '#f8d7da', color: resultadoTipo === 'success' ? '#0f5132' : '#842029' }">
                    {{ resultadoMensaje }}
                </div>
            </div>

            <!-- TARJETA 2: CONFIGURACIÓN SFTP -->
            <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                <h3 style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px;">🕒 Horario de Inyección SFTP</h3>
                
                <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 5px;">Frecuencia de entrega:</label>
                <select v-model="configuracionSFTP.dia" style="width: 100%; padding: 10px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; background: white;">
                    <option value="Lunes">Todos los días LUNES</option>
                    <option value="Martes">Todos los días MARTES</option>
                    <option value="Miercoles">Todos los días MIÉRCOLES</option>
                    <option value="Jueves">Todos los días JUEVES</option>
                    <option value="Viernes">Todos los días VIERNES</option>
                    <option value="Diario">Todos los días (L-V)</option>
                </select>

                <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 5px;">Hora límite de carga:</label>
                <input type="time" v-model="configuracionSFTP.hora" style="width: 100%; padding: 10px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;" />

                <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 5px;">Ruta propuesta SFTP:</label>
                <input type="text" v-model="configuracionSFTP.ruta" placeholder="Ej: in/gestiones/mes_año" style="width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;" />
            </div>

        </div>

        <!-- COLUMNA DERECHA: CONSTRUCTOR Y PREVIEW -->
        <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
            <h3 style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px;">📝 Mapeador de Layouts Multimandante</h3>
            
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

            <!-- SIMULADOR EXCEL (PREVIEW) -->
            <div v-if="columnasLayout.length > 0" style="margin-bottom: 25px; border: 2px solid #198754; border-radius: 6px; overflow: hidden;">
                <div style="background: #198754; color: white; padding: 10px; font-weight: bold; font-size: 14px;">
                    📊 Previsualización del CSV Final (Simulación Excel)
                </div>
                <div style="overflow-x: auto; padding: 10px; background: #f8f9fa;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: center;">
                        <thead>
                            <tr style="background: #0d6efd; color: white;">
                                <th v-for="col in columnasLayout" :key="col.id" style="padding: 8px; border: 1px solid #dee2e6; white-space: nowrap;">{{ col.nombre }}</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr style="background: white;">
                                <td v-for="col in columnasLayout" :key="col.id" style="padding: 8px; border: 1px solid #dee2e6; color: #495057; white-space: nowrap;">
                                    {{ filaEjemplo[col.nombre] }}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
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