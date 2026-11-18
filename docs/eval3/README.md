# Evaluación 3: API pública → Excel → Correo → Mejora creativa

Robot sobre el caso semestral (banco **Altoro Mutual**, demo.testfire.net),
diseñado como **flujo secuencial con subprocesos anidados**. Los correos usan
el patrón **dispatcher / performer** con una cola y su tracker.

![Topología](topologia_mini.png)

Diagrama completo, con decisiones y manejo de errores: [`topologia.png`](topologia.png).

## Funciona en cualquier PC

- **Los `.bat` no tienen rutas fijas.** Encuentran el repo solos y usan `%USERPROFILE%\Rocketbot_Salida` como carpeta de salida. Es `C:\Users\bpalm\...` en el PC de Benjamín y la carpeta del usuario de Gustavo en el suyo.
- **Los `.bat` no necesitan argumentos.** Cada uno toma el archivo más reciente que dejó el paso anterior.
- **Lo propio de cada PC va en `config/config.json`.** Ahí van la clave del correo y la ruta de Rocketbot; ese archivo no se sube a GitHub. La plantilla es [`config/config.eval3.example.json`](../../config/config.eval3.example.json).
- **En Rocketbot hay una sola variable**: `ruta_repo`, la carpeta donde está clonado el repo. Si en los dos PCs se clona en `C:\Workspace\rpa_testfire\rpa_testfire`, no hay que cambiar nada.

## Pasos del robot en Rocketbot

Cada paso con `.bat` es un comando **Ejecutar archivo** con la ruta `{ruta_repo}\scripts\<nombre>.bat`, seguido de un **Ejecutar Python** que lee el resultado (ver más abajo).

| # | Subproceso | En Rocketbot | Resultado |
|---|---|---|---|
| 0 | Inicio | Asignar `ruta_repo` | — |
| 1 | Login | Robot v5 (sin cambios) | Sesión en TestFire |
| 2a | Extracción | Robot v5 → guarda `consolidado.xlsx` en `Rocketbot_Salida` | `consolidado.xlsx` |
| 2b | Conciliación | `conciliar_rocketbot.bat` | `discrepancias_X.xlsx` |
| 2c | API del dólar | `referencia_externa.bat` | `api_dolar_X.json` + `reporte_final_X.xlsx` |
| 3 | Excel en escritorio | Comandos Excel: abrir `reporte_final_X.xlsx`, ir a "Referencia externa", captura, guardar y **cerrar** | Evidencia IL 3.2 |
| 4a | Dispatcher | `dispatcher.bat` | Correos en la cola |
| 4b | Performer | `performer.bat` (envío real por SMTP) | Correos enviados + hoja "Seguimiento de envíos" |
| 4c | Correo al supervisor | `resumen_supervisor.bat` → **Configurar servidor** + **Enviar email SMTP** con `{para}`, `{asunto}`, `{mensaje}`, `{adjunto}` | Correo con el reporte adjunto |
| 4d | Recepción | **Listar email nuevos IMAP** (para mostrarlo) + `clasificar.bat` | Respuestas en RPA_APROBADO / RPA_RECHAZADO / RPA_REVISAR |
| 5 | Cierre | Mensaje final con los totales | — |

### Leer el resultado de cada `.bat` (comando Ejecutar Python)

Cada `.bat` deja una línea JSON en `Rocketbot_Salida\<nombre>_stdout.log`. Los errores quedan en `<nombre>_errores.log`. Este bloque se copia en el **Ejecutar Python** que va después de cada `.bat`, cambiando solo el nombre del log:

```python
import json, os
salida = os.path.join(os.path.expanduser("~"), "Rocketbot_Salida")
with open(os.path.join(salida, "performer_stdout.log"), encoding="utf-8") as archivo:
    datos = json.loads(archivo.read().strip().splitlines()[-1])
SetVar("paso_ok", "1" if datos.get("ok") else "0")
SetVar("paso_detalle", json.dumps(datos, ensure_ascii=False))
```

Después, un **If** con `{paso_ok} == "0"` lleva al cierre con error. Ese es el manejo de errores entre subprocesos.

Para el correo al supervisor (4c), el mismo bloque con `resumen_supervisor_stdout.log`, agregando:

```python
SetVar("para", datos["para"])
SetVar("asunto", datos["asunto"])
SetVar("mensaje", datos["mensaje"])
SetVar("adjunto", datos["adjunto"])
```

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
