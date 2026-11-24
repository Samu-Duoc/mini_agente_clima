# Estado actual, funcionalidades pendientes y mejoras proyectadas del robot supervisor

## 1. Alcance y criterio de evaluación

Este informe diferencia entre funcionalidades implementadas, probadas, parcialmente
implementadas y pendientes. Una afirmación queda marcada como probada únicamente
cuando existen pruebas observables o evidencia persistida en el backend, el estado
local o los logs. El mini agente conserva Rocketbot como componente de ejecución,
pero durante esta etapa no debe iniciar el ejecutable ni Chrome/Selenium.

## 2. Funcionalidades implementadas y probadas

### Comunicación persistente y cola de trabajos

Se implementaron y probaron una cola persistente en Neon y los módulos de
comunicación del mini agente. Entre las funciones probadas se encuentran:

- autenticación independiente mediante `AGENT_API_KEY`;
- consulta de trabajos pendientes;
- reclamo exclusivo mediante bloqueos de base de datos;
- heartbeat periódico;
- registro de inicio y finalización;
- prevención de solicitudes duplicadas mediante `clave_solicitud`;
- recuperación controlada ante desconexión de FastAPI;
- bloqueo local para impedir dos instancias del mismo agente;
- cierre seguro mediante `Ctrl+C`;
- persistencia del estado del agente en `.agent_state.json`.

Las pruebas registraron respuestas autenticadas y el rechazo sin credenciales.
También se comprobó que un trabajo reclamado no fue reclamado simultáneamente por
otro agente y que una solicitud duplicada no creó otro trabajo.

### Persistencia de estados y eventos

FastAPI dispone de las tablas `trabajos_robot`, `estado_supervisor` y
`eventos_supervisor`. Se probaron estados de reclamo, inicio, finalización,
heartbeat y error. Cada evento relevante puede asociarse a una fecha, un agente y,
cuando corresponde, un identificador de trabajo.

### DRY_RUN

El modo `DRY_RUN=true` se probó con el lanzador oficial del ejecutable y la
identificación de `Clima` y `robot.db`. La prueba confirmó que ambos archivos
existen y construyó el comando de Rocketbot, sin iniciarlo. No abrió Chrome ni
Selenium y no ejecutó el robot.

## 3. Funcionalidades parcialmente implementadas

### Ejecución de Rocketbot desde el supervisor

Existe `rocketbot_runner.py`, que conoce el ejecutable, la base de datos, el
nombre del robot y la opción documentada `-start`. También conserva
`rocketbot_browser.py` como alternativa visual basada en Selenium.

Sin embargo, la ejecución real no está probada y mantiene las banderas
`DRY_RUN=true` y `ALLOW_REAL_EXECUTION=false`. No existe evidencia de que
Rocketbot Development permita ejecución desatendida compatible. Por ello,
el supervisor no debe considerar un código de salida cero como prueba de éxito
del proceso completo.

Faltaría para completar esta funcionalidad:

- verificar el comportamiento real de la licencia Development;
- definir una señal verificable de éxito por cada ejecución;
- probar el lanzamiento real sin modificar scripts ni datos de producción;
- distinguir fallos del proceso, fallos internos del robot y timeout;
- validar el cierre y la limpieza de procesos creados por el supervisor.

### Recuperación automática de etapas fallidas

FastAPI puede registrar `etapa_actual`, `etapa_fallida` y `etapas_completadas`.
Se añadió el endpoint de etapas y se probó que una etapa completada se añadió al
historial y que no pudo solicitarse otra recuperación cuando ya figuraba como
completada.

Esta recuperación no es todavía completa: no existen subprocesos independientes
para clima, sismos, Excel, Drive, recepción API o correo. El robot `Clima`
contiene el flujo completo dentro de 18 comandos, mientras `Clima_Sismos` es una
navegación auxiliar y no representa el flujo completo.

Faltaría:

- identificar las señales reales de finalización de cada etapa;
- separar o invocar etapas reales de Rocketbot;
- almacenar contexto por etapa;
- definir un plan de reanudación compatible con el robot;
- probar el límite máximo de tres intentos sin repetir etapas completadas.

### Programación y ejecución en segundo plano

El proceso Python puede ejecutarse manualmente y posee bloqueo local y cierre
seguro. También puede mantener un ciclo periódico de heartbeat y consulta.

No está comprobado como servicio persistente de Windows, no se ha configurado
inicio automático y no existe evidenciación del arranque como proceso
desatendido. Tampoco se ha probado ejecución real sin ventanas.

Faltaría preparar y validar el inicio manual estable, posteriormente decidir si
un servicio de Windows o tarea programada es compatible y seguro.

### Notificaciones de errores

Los logs locales contienen fecha, hora, identificadores y resultados de errores.
FastAPI registra eventos y estados del supervisor. Sin embargo, la notificación
por correo o mensajes externos no está implementada ni probada.

Faltaría definir qué canal usar para alertas, qué severidad corresponde a cada
estado y qué datos se pueden enviar sin exponer secretos.

## 4. Funcionalidades pendientes de desarrollo

- división de `Clima` en subprocesos realmente independientes;
- ejecución real controlada desde el supervisor;
- recuperación automática por etapa;
- confirmación real de finalización de clima, sismos, Excel, Drive, API y correo;
- publicación de alertas externas al Dashboard o correo;
- inicio automático como servicio o tarea programada de Windows;
- pruebas de reinicio con un trabajo activo y estado remoto desconocido;
- pruebas de máximo de reintentos en producción controlada;
- protección adicional contra pérdida de mensajes entre FastAPI y el agente.

## 5. Mejoras proyectadas

Las siguientes mejoras tienen mayor viabilidad técnica y podrían integrarse antes
de una presentación:

- modo supervisor de solo monitoreo, sin iniciar Rocketbot;
- vista consolidada de heartbeats y eventos;
- códigos de alerta con identificador de trabajo y etapa;
- panel de estados `PENDIENTE`, `RECLAMADO`, `EN_EJECUCION`,
  `ESTADO_NO_CONFIRMADO`, `EJECUCION_ERROR` y `COMPLETADO`;
- reglas explícitas para intervención humana;
- registro local inmutable de alertas;
- exportación futura de los eventos a reportes.

Estas mejoras requieren evidencia adicional antes de calificarse como disponibles
para ejecución real.

## 6. Estado de preparación para entrega

El proyecto está preparado para supervisión, coordinación persistente y pruebas
DRY_RUN. No está listo para afirmar ejecución desatendida ni recuperación
automática real de Rocketbot.
