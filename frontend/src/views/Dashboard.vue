<script setup>
import { ref, onMounted, onUnmounted } from 'vue'; 
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
// RELOJ OFICIAL DEL SERVIDOR EN VIVO
// ==========================================
const horaServidorVisual = ref('Cargando hora...');
let intervaloReloj = null;

const iniciarRelojSincronizado = async () => {
    try {
        const respuesta = await axios.get('/api/server-time');
        
        if (respuesta.data.success) {
            let horaActual = new Date(respuesta.data.server_time);
            
            intervaloReloj = setInterval(() => {
                horaActual.setSeconds(horaActual.getSeconds() + 1);
                
                const horas = String(horaActual.getHours()).padStart(2, '0');
                const minutos = String(horaActual.getMinutes()).padStart(2, '0');
                const segundos = String(horaActual.getSeconds()).padStart(2, '0');
                
                horaServidorVisual.value = `${horas}:${minutos}:${segundos}`;
            }, 1000);
        }
    } catch (error) {
        horaServidorVisual.value = 'Error al sincronizar';
        console.error("No se pudo obtener la hora del servidor", error);
    }
};

onUnmounted(() => {
    if (intervaloReloj) clearInterval(intervaloReloj);
});

// ==========================================
// ESTADOS DE COLLAPSE (Para encoger tarjetas)
// ==========================================
const showRobot = ref(true);
const showManuales = ref(true); // Nueva tarjeta de herramientas manuales
const showVicidial = ref(false); // La cerramos por defecto para ahorrar espacio
const showSFTP = ref(false); // La cerramos por defecto
const showMotorSQL = ref(true);

// ==========================================
// LÓGICA DEL ROBOT ETL (DÍA ACTUAL)
// ==========================================
const ejecutando = ref(false);
const descargando = ref(false);
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

const descargarUltimoArchivo = async () => {
    descargando.value = true;
    try {
        const response = await axios.get(`/api/descargar-ultimo/${mandanteActivo.value}`, {
            responseType: 'blob'
        });
        
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `${mandanteActivo.value.toUpperCase()}_GESTIONES_ULTIMO.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    } catch (error) {
        alert("No se encontró ningún archivo generado o hubo un error en la descarga.");
    } finally {
        descargando.value = false;
    }
};

// ==========================================
// LÓGICA DE HERRAMIENTAS MANUALES (A y B)
// ==========================================
const rescateInicio = ref('');
const rescateFin = ref('');
const rescatando = ref(false);

const exportInicio = ref('');
const exportFin = ref('');
const exportando = ref(false);

const ejecutarRescateVicidial = async () => {
    if (!rescateInicio.value || !rescateFin.value) {
        alert("⚠️ Por favor, selecciona una fecha de inicio y una de fin.");
        return;
    }
    if (rescateInicio.value > rescateFin.value) {
        alert("⚠️ La fecha de inicio no puede ser mayor que la de fin.");
        return;
    }

    rescatando.value = true;
    resultadoMensaje.value = '';
    
    try {
        // Llamaremos a una nueva ruta en app.py diseñada para bucles
        const respuesta = await axios.post('/api/robot/rescate', {
            cliente: mandanteActivo.value,
            fecha_inicio: rescateInicio.value,
            fecha_fin: rescateFin.value
        });
        resultadoTipo.value = 'success';
        resultadoMensaje.value = respuesta.data.message;
    } catch (error) {
        resultadoTipo.value = 'error';
        resultadoMensaje.value = error.response?.data?.message || 'Error en el rescate de datos.';
    } finally {
        rescatando.value = false;
    }
};

const generarConsolidadoHistorico = async () => {
    if (!exportInicio.value || !exportFin.value) {
        alert("⚠️ Por favor, selecciona el rango de fechas para el consolidado.");
        return;
    }
    if (exportInicio.value > exportFin.value) {
        alert("⚠️ La fecha de inicio no puede ser mayor que la de fin.");
        return;
    }

    exportando.value = true;
    try {
        // Llamaremos a una nueva ruta GET en app.py que exporta desde Postgres directo
        const response = await axios.get(`/api/exportar-historico/${mandanteActivo.value}`, {
            params: {
                inicio: exportInicio.value,
                fin: exportFin.value
            },
            responseType: 'blob'
        });
        
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `${mandanteActivo.value.toUpperCase()}_CONSOLIDADO_${exportInicio.value}_al_${exportFin.value}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    } catch (error) {
        alert("❌ Error al generar el consolidado histórico. Revisa que haya datos en ese rango.");
    } finally {
        exportando.value = false;
    }
};

// ==========================================
// LÓGICA DEL MOTOR SQL, SFTP Y VICIDIAL
// ==========================================
const mandanteActivo = ref('hites');

const prefijoCampana = ref('HIT');
const consultaSQL = ref(`SELECT * FROM gestiones;`); // Default simple

const diasSeleccionados = ref(['fri']);

const configuracionSFTP = ref({
    dia: 'fri',
    hora: '21:00',
    ruta: 'gestiones/mes_año',
    dia_inicio_ciclo: 5,
    tipo_extraccion: 'semanal' 
});

const guardandoLayout = ref(false);
const mensajeLayout = ref('');

const viciConfig = ref({ url: '', username: '', password: '' });
const guardandoVici = ref(false);
const mensajeVici = ref('');

const cargarConfiguraciones = async () => {
    mensajeLayout.value = ''; 
    try {
        const respuestaLayout = await axios.get(`/api/layout/${mandanteActivo.value}`);
        if (respuestaLayout.data.success && respuestaLayout.data.prefijo_campana) {
            prefijoCampana.value = respuestaLayout.data.prefijo_campana;
            consultaSQL.value = respuestaLayout.data.consulta_sql;
            
            const sftpDB = respuestaLayout.data.sftp;
            configuracionSFTP.value.hora = sftpDB.hora || '21:00';
            configuracionSFTP.value.ruta = sftpDB.ruta || 'gestiones/mes_año';
            configuracionSFTP.value.dia_inicio_ciclo = sftpDB.dia_inicio_ciclo !== undefined ? sftpDB.dia_inicio_ciclo : 5;
            configuracionSFTP.value.tipo_extraccion = sftpDB.tipo_extraccion || 'semanal';
            
            let rawDia = sftpDB.dia || 'fri';
            const diasMapReverse = {
                'Todos los días LUNES': ['mon'],
                'Todos los días MARTES': ['tue'],
                'Todos los días MIÉRCOLES': ['wed'],
                'Todos los días JUEVES': ['thu'],
                'Todos los días VIERNES': ['fri'],
                'Todos los días SÁBADO': ['sat'],
                'Todos los días DOMINGO': ['sun'],
                'Todos los días (L-V)': ['mon', 'tue', 'wed', 'thu', 'fri'],
                'Todos los días (L-D)': ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'],
                'Diario': ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'],
                'mon-fri': ['mon', 'tue', 'wed', 'thu', 'fri'],
                'mon-sun': ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
            };

            if (diasMapReverse[rawDia]) {
                diasSeleccionados.value = diasMapReverse[rawDia];
            } else {
                diasSeleccionados.value = rawDia.split(',');
            }
        }

        const respuestaVici = await axios.get('/api/config/vicidial');
        if (respuestaVici.data.success) {
            viciConfig.value.url = respuestaVici.data.url;
            viciConfig.value.username = respuestaVici.data.username;
            viciConfig.value.password = respuestaVici.data.password;
        }
    } catch (error) {
        console.error("Error al cargar configuraciones:", error);
    }
};

onMounted(() => {
    cargarConfiguraciones();
    iniciarRelojSincronizado(); 
});

const guardarMotorSQL = async () => {
    guardandoLayout.value = true;
    mensajeLayout.value = '';
    
    let cronString = diasSeleccionados.value.join(',');
    
    if (diasSeleccionados.value.length === 5 && !diasSeleccionados.value.includes('sat') && !diasSeleccionados.value.includes('sun')) {
        cronString = 'mon-fri';
    } else if (diasSeleccionados.value.length === 7) {
        cronString = 'mon-sun';
    }

    configuracionSFTP.value.dia = cronString;

    try {
        await axios.post(`/api/layout/${mandanteActivo.value}/guardar`, {
            prefijo_campana: prefijoCampana.value,
            consulta_sql: consultaSQL.value,
            sftp: configuracionSFTP.value
        });
        mensajeLayout.value = `✅ Configuración maestra guardada para ${mandanteActivo.value.toUpperCase()}.`;
    } catch (error) {
        mensajeLayout.value = '❌ Error al guardar en la base de datos';
    } finally {
        guardandoLayout.value = false;
        setTimeout(() => { mensajeLayout.value = '' }, 4000);
    }
};

const guardarVicidial = async () => {
    guardandoVici.value = true;
    mensajeVici.value = '';
    try {
        await axios.post('/api/config/vicidial/guardar', viciConfig.value);
        mensajeVici.value = `✅ Credenciales guardadas.`;
    } catch (error) {
        mensajeVici.value = '❌ Error al guardar credenciales.';
    } finally {
        guardandoVici.value = false;
        setTimeout(() => { mensajeVici.value = '' }, 4000);
    }
};
</script>

<template>
  <div style="font-family: sans-serif; padding: 20px; background-color: #e9ecef; min-height: 100vh; box-sizing: border-box;">
    
    <!-- Barra de navegación -->
    <nav style="background: #212529; color: white; padding: 15px 25px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h3 style="margin: 0; display: flex; align-items: center; gap: 10px;">
            ⚙️ SISTEMA ROOT 
            <span style="font-size: 14px; font-weight: normal; color: #adb5bd; border-left: 1px solid #495057; padding-left: 10px;">Panel de Control</span>
        </h3>
        
        <div style="display: flex; align-items: center; gap: 20px;">
            <!-- RELOJ DIGITAL -->
            <div style="background: #000; padding: 5px 15px; border-radius: 4px; border: 1px solid #333; font-family: monospace; font-size: 16px; color: #00ffcc; letter-spacing: 1px; display: flex; flex-direction: column; align-items: center;">
                <span style="font-size: 10px; color: #aaa; letter-spacing: 0;">HORA OFICIAL DEL SERVIDOR</span>
                {{ horaServidorVisual }}
            </div>

            <span style="font-weight: bold;">👋 Hola, {{ usuarioActual }}</span>
            <button @click="cerrarSesion" style="background: #dc3545; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; font-weight: bold;">Cerrar Sesión</button>
        </div>
    </nav>

    <!-- Contenedor Principal -->
    <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 20px;">
        
        <!-- COLUMNA IZQUIERDA -->
        <div style="display: flex; flex-direction: column; gap: 20px;">
            
            <!-- TARJETA 1: ROBOT AUTOMÁTICO -->
            <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                <h3 @click="showRobot = !showRobot" style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; cursor: pointer; display: flex; justify-content: space-between;">
                    🤖 Robot ETL (Extracción Diaria) <span>{{ showRobot ? '🔼' : '🔽' }}</span>
                </h3>
                
                <div v-show="showRobot">
                    <p style="color: #6c757d; margin-bottom: 15px; font-size: 14px;">
                        Dispara el Robot de forma manual para forzar la extracción configurada del día de hoy.
                    </p>
                    
                    <button 
                        @click="ejecutarRobot" 
                        :disabled="ejecutando || rescatando"
                        style="padding: 14px 24px; color: white; border: none; border-radius: 6px; font-weight: bold; width: 100%; cursor: pointer; margin-bottom: 10px;"
                        :style="{ backgroundColor: ejecutando ? '#6c757d' : '#0d6efd' }"
                    >
                        <span v-if="ejecutando">⏳ Ejecutando Extracción del día...</span>
                        <span v-else>▶️ INICIAR ROBOT {{ mandanteActivo.toUpperCase() }} (HOY)</span>
                    </button>

                    <button 
                        @click="descargarUltimoArchivo" 
                        :disabled="descargando || ejecutando || rescatando"
                        style="padding: 12px; background: #198754; color: white; border: none; border-radius: 6px; font-weight: bold; width: 100%; cursor: pointer;"
                    >
                        {{ descargando ? '📥 Descargando...' : '📥 Descargar Último Archivo Inyectado' }}
                    </button>

                    <div v-if="resultadoMensaje" style="margin-top: 15px; padding: 10px; border-radius: 6px; font-weight: bold; text-align: center;"
                        :style="{ backgroundColor: resultadoTipo === 'success' ? '#d1e7dd' : '#f8d7da', color: resultadoTipo === 'success' ? '#0f5132' : '#842029' }">
                        {{ resultadoMensaje }}
                    </div>
                </div>
            </div>

            <!-- NUEVA TARJETA 1.5: HERRAMIENTAS MANUALES AVANZADAS -->
            <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-left: 4px solid #ffc107;">
                <h3 @click="showManuales = !showManuales" style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; cursor: pointer; display: flex; justify-content: space-between;">
                    🛠️ Herramientas Manuales <span>{{ showManuales ? '🔼' : '🔽' }}</span>
                </h3>
                
                <div v-show="showManuales" style="display: flex; flex-direction: column; gap: 20px; margin-top: 15px;">
                    
                    <!-- HERRAMIENTA A: EL MINERO -->
                    <div style="background: #fff3cd; padding: 15px; border-radius: 6px; border: 1px solid #ffe69c;">
                        <h4 style="margin: 0 0 5px 0; color: #664d03;">⛏️ Herramienta A: Rescate Vicidial</h4>
                        <p style="font-size: 12px; color: #664d03; margin-top: 0;">Obliga al robot a ir a Vicidial a descargar días pasados (Ej: Se cayó el servidor el fin de semana).</p>
                        
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                            <div>
                                <label style="font-size: 11px; font-weight: bold; color: #664d03;">Inicio:</label>
                                <input type="date" v-model="rescateInicio" style="width: 100%; padding: 6px; border: 1px solid #ccc; border-radius: 4px;" />
                            </div>
                            <div>
                                <label style="font-size: 11px; font-weight: bold; color: #664d03;">Fin:</label>
                                <input type="date" v-model="rescateFin" style="width: 100%; padding: 6px; border: 1px solid #ccc; border-radius: 4px;" />
                            </div>
                        </div>
                        
                        <button 
                            @click="ejecutarRescateVicidial" 
                            :disabled="rescatando || ejecutando"
                            style="width: 100%; padding: 10px; background: #ffca2c; color: #000; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;"
                        >
                            {{ rescatando ? '⏳ Extrañendo datos...' : 'Forzar Extracción Vicidial' }}
                        </button>
                    </div>

                    <!-- HERRAMIENTA B: LA BÓVEDA -->
                    <div style="background: #e2e3e5; padding: 15px; border-radius: 6px; border: 1px solid #d3d6d8;">
                        <h4 style="margin: 0 0 5px 0; color: #41464b;">📦 Herramienta B: Exportador Histórico</h4>
                        <p style="font-size: 12px; color: #41464b; margin-top: 0;">Arma un CSV gigante al instante usando los datos que ya están en la base local (No usa Vicidial).</p>
                        
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                            <div>
                                <label style="font-size: 11px; font-weight: bold; color: #41464b;">Inicio:</label>
                                <input type="date" v-model="exportInicio" style="width: 100%; padding: 6px; border: 1px solid #ccc; border-radius: 4px;" />
                            </div>
                            <div>
                                <label style="font-size: 11px; font-weight: bold; color: #41464b;">Fin:</label>
                                <input type="date" v-model="exportFin" style="width: 100%; padding: 6px; border: 1px solid #ccc; border-radius: 4px;" />
                            </div>
                        </div>
                        
                        <button 
                            @click="generarConsolidadoHistorico" 
                            :disabled="exportando"
                            style="width: 100%; padding: 10px; background: #6c757d; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;"
                        >
                            {{ exportando ? '⏳ Generando archivo...' : 'Descargar Consolidado CSV' }}
                        </button>
                    </div>

                </div>
            </div>

            <!-- TARJETA 2: CREDENCIALES VICIDIAL (Colapsada por defecto para ahorrar espacio visual) -->
            <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                <h3 @click="showVicidial = !showVicidial" style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; cursor: pointer; display: flex; justify-content: space-between;">
                    🔐 Accesos Vicidial <span>{{ showVicidial ? '🔼' : '🔽' }}</span>
                </h3>
                
                <div v-show="showVicidial">
                    <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 5px;">URL de Exportación:</label>
                    <input type="text" v-model="viciConfig.url" placeholder="https://vicieffectiva..." style="width: 100%; padding: 10px; margin-bottom: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;" />

                    <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 5px;">Usuario:</label>
                    <input type="text" v-model="viciConfig.username" style="width: 100%; padding: 10px; margin-bottom: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;" />

                    <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 5px;">Contraseña:</label>
                    <input type="password" v-model="viciConfig.password" style="width: 100%; padding: 10px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;" />

                    <button 
                        @click="guardarVicidial" 
                        :disabled="guardandoVici" 
                        style="width: 100%; padding: 10px; background: #0dcaf0; color: #000; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;"
                    >
                        {{ guardandoVici ? 'Guardando...' : 'Guardar Credenciales' }}
                    </button>
                    <div v-if="mensajeVici" style="margin-top: 10px; text-align: center; font-weight: bold; padding: 8px; background: #d1e7dd; color: #0f5132; border-radius: 4px; font-size: 13px;">
                        {{ mensajeVici }}
                    </div>
                </div>
            </div>

            <!-- TARJETA 3: CONFIGURACIÓN SFTP (Colapsada por defecto) -->
            <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                <h3 @click="showSFTP = !showSFTP" style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; cursor: pointer; display: flex; justify-content: space-between;">
                    🕒 Configuración y Horario <span>{{ showSFTP ? '🔼' : '🔽' }}</span>
                </h3>
                
                <div v-show="showSFTP">
                    
                    <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 10px;">Modo de Extracción (Cerebro Automático):</label>
                    <div style="display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; background: #e3f2fd; padding: 12px; border-radius: 6px; border: 1px solid #90caf9;">
                        <label style="cursor: pointer; font-size: 14px; display: flex; align-items: flex-start; gap: 8px;">
                            <input type="radio" value="semanal" v-model="configuracionSFTP.tipo_extraccion" style="margin-top: 3px;"> 
                            <div>
                                <strong>Acumulado Semanal (Consolidado)</strong><br>
                                <span style="font-size: 12px; color: #555;">Suma los días desde el inicio del ciclo. Ideal para cierres de semana.</span>
                            </div>
                        </label>
                        <label style="cursor: pointer; font-size: 14px; display: flex; align-items: flex-start; gap: 8px;">
                            <input type="radio" value="diario" v-model="configuracionSFTP.tipo_extraccion" style="margin-top: 3px;"> 
                            <div>
                                <strong>Transaccional Diario Puro</strong><br>
                                <span style="font-size: 12px; color: #555;">Extrae y envía única y exclusivamente las gestiones del día.</span>
                            </div>
                        </label>
                    </div>

                    <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 10px;">Días de Ejecución (FTP):</label>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 15px; background: #f8f9fa; padding: 10px; border-radius: 6px; border: 1px solid #dee2e6;">
                        <label style="cursor: pointer; font-size: 14px;"><input type="checkbox" value="mon" v-model="diasSeleccionados"> Lunes</label>
                        <label style="cursor: pointer; font-size: 14px;"><input type="checkbox" value="tue" v-model="diasSeleccionados"> Martes</label>
                        <label style="cursor: pointer; font-size: 14px;"><input type="checkbox" value="wed" v-model="diasSeleccionados"> Miércoles</label>
                        <label style="cursor: pointer; font-size: 14px;"><input type="checkbox" value="thu" v-model="diasSeleccionados"> Jueves</label>
                        <label style="cursor: pointer; font-size: 14px;"><input type="checkbox" value="fri" v-model="diasSeleccionados"> Viernes</label>
                        <label style="cursor: pointer; font-size: 14px;"><input type="checkbox" value="sat" v-model="diasSeleccionados"> Sábado</label>
                        <label style="cursor: pointer; font-size: 14px;"><input type="checkbox" value="sun" v-model="diasSeleccionados"> Domingo</label>
                    </div>

                    <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 5px;">
                        Día de Inicio de Campaña (Para Modo Consolidado):
                    </label>
                    <div style="margin-bottom: 15px;">
                        <select 
                            v-model="configuracionSFTP.dia_inicio_ciclo" 
                            :disabled="configuracionSFTP.tipo_extraccion === 'diario'"
                            style="width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; background: white; font-weight: bold;"
                            :style="{ backgroundColor: configuracionSFTP.tipo_extraccion === 'diario' ? '#e9ecef' : 'white' }"
                        >
                            <option :value="0">Lunes</option>
                            <option :value="1">Martes</option>
                            <option :value="2">Miércoles</option>
                            <option :value="3">Jueves</option>
                            <option :value="4">Viernes</option>
                            <option :value="5">Sábado</option>
                            <option :value="6">Domingo</option>
                        </select>
                    </div>

                    <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 5px;">Hora límite de carga:</label>
                    <input type="time" v-model="configuracionSFTP.hora" style="width: 100%; padding: 10px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;" />

                    <label style="font-size: 13px; font-weight: bold; color: #666; display: block; margin-bottom: 5px;">Ruta propuesta SFTP:</label>
                    <input type="text" v-model="configuracionSFTP.ruta" placeholder="Ej: gestiones/mes_año" style="width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;" />
                </div>
            </div>

        </div>

        <!-- COLUMNA DERECHA: MOTOR SQL -->
        <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
            <h3 @click="showMotorSQL = !showMotorSQL" style="margin-top: 0; color: #212529; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; cursor: pointer; display: flex; justify-content: space-between;">
                📝 Motor de Procesamiento SQL <span>{{ showMotorSQL ? '🔼' : '🔽' }}</span>
            </h3>
            
            <div v-show="showMotorSQL">
                <!-- SELECTOR DE MANDANTE ACTIVO -->
                <div style="margin-bottom: 20px; background: #f8f9fa; padding: 15px; border-radius: 6px; border: 1px solid #dee2e6;">
                    <label style="font-weight: bold; color: #495057; display: block; margin-bottom: 8px;">🏢 Seleccionar Mandante a Configurar:</label>
                    <select 
                        v-model="mandanteActivo" 
                        @change="cargarConfiguraciones"
                        style="width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 4px; font-size: 15px; font-weight: bold; background-color: white; cursor: pointer;"
                    >
                        <option value="hites">Hites (Cartera Retail)</option>
                        <option value="ripley">Ripley (Cobranza Activa)</option>
                        <option value="lider">Líder / BCI (Prendario)</option>
                    </select>
                </div>

                <!-- PREFIJO DE CAMPAÑA -->
                <div style="margin-bottom: 20px;">
                    <label style="font-size: 14px; font-weight: bold; color: #495057; display: block; margin-bottom: 5px;">
                        🔍 Prefijo de Campaña (Filtro)
                    </label>
                    <p style="font-size: 12px; color: #6c757d; margin-top: 0; margin-bottom: 5px;">El robot extraerá de la tabla cruda cualquier gestión cuya campaña empiece con este texto.</p>
                    <input 
                        type="text" 
                        v-model="prefijoCampana" 
                        placeholder="Ej: HIT" 
                        style="width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 16px; font-weight: bold;" 
                    />
                </div>

                <!-- CONSOLA SQL -->
                <div style="margin-bottom: 20px;">
                    <label style="font-size: 14px; font-weight: bold; color: #495057; display: block; margin-bottom: 5px;">
                        💻 Consulta PostgreSQL de Transformación (El Layout)
                    </label>
                    <p style="font-size: 12px; color: #6c757d; margin-top: 0; margin-bottom: 5px;">Escribe el SELECT para armar tu CSV final. Los nombres de las columnas que pongas aquí serán las cabeceras exactas del CSV. La tabla base se llama <strong>gestiones_raw</strong>.</p>
                    
                    <textarea 
                        v-model="consultaSQL"
                        spellcheck="false"
                        style="width: 100%; height: 350px; padding: 15px; border: 1px solid #1e1e1e; border-radius: 4px; background-color: #1e1e1e; color: #00ffcc; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; line-height: 1.5; resize: vertical; box-sizing: border-box;"
                    ></textarea>
                </div>

                <!-- Botón Guardar Motor -->
                <button 
                    @click="guardarMotorSQL"
                    :disabled="guardandoLayout || !consultaSQL.trim()"
                    style="width: 100%; padding: 12px; background: #ffc107; color: #000; border: none; border-radius: 4px; font-weight: bold; font-size: 16px; cursor: pointer;"
                >
                    {{ guardandoLayout ? 'Guardando en BD...' : '💾 Guardar Configuración de Mandante' }}
                </button>

                <!-- Mensaje de éxito/error -->
                <div v-if="mensajeLayout" style="margin-top: 15px; text-align: center; font-weight: bold; padding: 10px; background: #d1e7dd; color: #0f5132; border-radius: 4px;">
                    {{ mensajeLayout }}
                </div>
            </div>
        </div>

    </div>
  </div>
</template>