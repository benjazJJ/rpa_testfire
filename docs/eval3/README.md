# Evaluación 3: API pública → Excel → Correo → Mejora creativa

Robot sobre el caso semestral (banco **Altoro Mutual**, demo.testfire.net),
diseñado como **flujo secuencial con subprocesos anidados**. Los correos usan
el patrón **dispatcher / performer** con una cola y su tracker.

![Topología](topologia_mini.png)

Diagrama completo, con decisiones y manejo de errores: [`topologia.png`](topologia.png).

## El robot de Rocketbot

`rocketbot/RPA_TestFire_Eval3.json` se importa en Rocketbot Studio. Está construido sobre el v5 (`rocketbot/RPA_TestFire_Login_v5.json`): el login y la extracción son los mismos, y la conciliación y el resto de los subprocesos se encadenan después.

| Línea | Subproceso | Qué hace |
|---|---|---|
| 1 a 6 | 1 · Login + extracción | Igual que el v5. Si la validación de filas y columnas da OK, deja `extraccion_ok = True` |
| 7 | 2b · Conciliación | `conciliar_rocketbot.bat` |
| 8 | 2c · API pública | `referencia_externa.bat`: dólar de mindicador.cl → `reporte_final_X.xlsx` |
| 9 | 3 · Excel | `abrir_excel.bat`: abre el libro en Excel, captura de pantalla, guarda y cierra |
| 10 | 4a · Dispatcher | `dispatcher.bat` |
| 11 | 4b · Performer | `performer.bat`: envío real por SMTP |
| 12 | 4c · Correo al supervisor | `resumen_supervisor.bat` + comandos **Configurar servidor** y **Enviar email SMTP** de Rocketbot |
| 13 | 4d · Recepción y clasificación | `clasificar.bat` (lee por IMAP y mueve a carpetas) |
| 14 | 5 · Cierre | Mensaje final OK o con errores |

**Cómo encadena los pasos.** Cada subproceso es un `If {continuar}`. Adentro tiene tres comandos:
- **Ejecutar archivo** del `.bat`. Lo que el `.bat` imprime queda en `{res_...}`.
- Un **If** que revisa si ese texto trae `RESULTADO=OK`.
- Si no lo trae, un **log de error** y `continuar = False`. Los subprocesos siguientes no corren y el cierre informa "fin CON ERRORES".

**Correo en Rocketbot.** El bloque 12 trae los comandos **Configurar servidor** y **Enviar email SMTP**, ya configurados:
- Para: `{correo_supervisor}`
- Asunto: `[RPA TestFire] Resumen de ejecución`
- Mensaje: `{mensaje_supervisor}`
- Adjunto: `{ruta_salida}\\reporte_final_ultimo.xlsx`

La recepción y la clasificación las hace `clasificar.bat` (bloque 13).

**La clave del correo no está en el repo.** En la copia de GitHub, *Configurar servidor* dice `COMPLETAR_CLAVE_DEL_CORREO`, porque el repo es público. El `.json` que se usa en cada PC lleva la clave real, o se escribe una vez en ese comando dentro de Rocketbot.

**Variables propias de cada PC** (pestaña *Variables* de Rocketbot):

| Variable | PC de Benjamín | PC de Gustavo |
|---|---|---|
| `ruta_repo` | `C:\Workspace\rpa_testfire\rpa_testfire` | Donde esté clonado el repo |
| `ruta_salida` | `C:\Users\bpalm\Rocketbot_Salida` | `C:\Users\<usuario>\Rocketbot_Salida` |
| `ruta_perfil_ff` | `C:/Users/bpalm/Rocketbot_FF_Profile` | `C:/Users/<usuario>/Rocketbot_FF_Profile` |
| `correo_supervisor` | `be.palmap@duocuc.cl` | El mismo u otro |

Nada más cambia entre PCs.
- Los `.bat` encuentran el repo solos y usan `%USERPROFILE%\Rocketbot_Salida`, que debe ser la misma carpeta que `ruta_salida`.
- Cada `.bat` toma el archivo más reciente que dejó el paso anterior.
- Lo demás va en `config/config.json`, que no se sube a GitHub. La plantilla está en `config/config.eval3.example.json`.

**Si algo falla**, el error de cada paso queda en `Rocketbot_Salida\<paso>_errores.log`.

## API pública: mindicador.cl

- `GET https://mindicador.cl/api/dolar`: pública, sin autenticación, datos del Banco Central.
- **Validaciones**: HTTP 200, JSON con `codigo = "dolar"`, serie no vacía y valor entre 300 y 3000 CLP.
- **Errores**: ante un timeout o un error 5xx hace 3 intentos (espera 1 s y 2 s); ante un 4xx o un JSON inválido no reintenta. Si todo falla, usa el último valor bueno en caché y lo marca en el Excel y en el log.
- **Resultado**: la columna `monto_clp` y la hoja "Referencia externa" en `reporte_final_X.xlsx`, más `api_dolar_X.json` como evidencia.

## Correo: SMTP e IMAP con el servidor del curso

**Envío (performer, SMTP SSL 465)**. Una sola conexión por corrida. Cada respuesta del servidor se traduce así:

| Respuesta del servidor | Estado del caso | Qué pasa |
|---|---|---|
| 250 OK | `ENVIADO` | — |
| 5xx destinatario (no existe, dirección mala) | `FALLIDO` | No se reintenta; sigue con el siguiente |
| 4xx, conexión cortada, timeout | `ERROR` | Se reintenta una vez al final; el resto queda para la próxima corrida (máximo 3 intentos) |
| Usuario o clave rechazados, remitente rechazado, servidor caído | — | Se detiene la corrida; los casos quedan en la cola |

**Recepción (`clasificar.bat`, IMAP SSL 993)**:
1. Busca en la bandeja las respuestas que traen `[RPA-TF #n]` en el asunto. Ese código lo pone el performer en cada correo.
2. Lee solo lo que escribió la persona: descarta el texto citado de Gmail, Outlook o el celular, que repite "APROBADO o RECHAZADO".
3. Decide APROBADO, RECHAZADO o REVISAR (si dice las dos palabras, ninguna, o no trae código).
4. Mueve la respuesta a su carpeta (la crea si no existe) y anota la decisión en el tracker.
5. `clasificar.bat solo-leer` muestra qué haría sin mover nada.

**Envío responsable**:
- Un correo por destinatario, con todas sus excepciones.
- Máximo 20 correos por ejecución (nunca más de 50) y 10 segundos entre correos.
- Las direcciones `@example.com` nunca salen por el canal real.

## Cola de correos (dispatcher / performer)

**Estados de cada caso**:
- `PENDIENTE`: en espera.
- `EN_PROCESO`: lo tomó un performer.
- `ENVIADO`: salió bien.
- `ERROR`: falla pasajera; se reintenta.
- `FALLIDO`: no se reintenta.

**Garantías**:
- **Un error no detiene la cola**: si falla el 401, sigue con el 402.
- **Retoma tras una caída**: si el robot se cae en el 600, la próxima corrida parte en el 601.
- **No duplica**: re-ejecutar el dispatcher no vuelve a encolar.
- **Admite performers en paralelo**: cada caso se toma con un UPDATE atómico.
- **Recupera casos atascados**: los que quedaron `EN_PROCESO` hace más de 15 minutos vuelven a `PENDIENTE`.

**Demo**: `demo_cola_1000.bat`, todo en modo simulación.

## Mejora creativa: ejecución programada con horario permitido

| Archivo | Qué hace |
|---|---|
| `crear_tarea_programada.bat [HH:MM]` | Crea la tarea "RPA TestFire Eval3" de lunes a viernes a las 09:00 (o a la hora indicada, para probar) |
| `ejecutar_robot.bat` | Lo corre la tarea. Revisa el horario permitido (lunes a viernes, 08:00 a 18:00) y lanza el robot con `rocketbot.exe -start=<robot> -db="<ruta>"` |
| `ejecutar_robot.bat --forzar` | Corre fuera de horario, y queda registrado que se forzó |

Fuera de horario no corre y deja el intento en el `.log` y en la Auditoría RPA, con el usuario de Windows, el PC y la hora.

## Logs: 3 niveles

| Nivel | Dónde | Qué |
|---|---|---|
| Auditoría RPA | Google Sheets (las mismas 12 columnas) | Un evento por fase |
| Archivo local | `logs/rpa_AAAAMMDD.log` | Todo, línea por línea; se escribe aunque no haya internet |
| Tracker | `data/cola/cola_correos.db` + hoja "Seguimiento de envíos" | Estado, intentos, error y respuesta de cada correo |
