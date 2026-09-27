# RPA Demo TestFire

Robot en Python (Selenium + Firefox) que inicia sesión en el sitio
bancario de demostración Altoro Mutual (TestFire), extrae los
movimientos recientes, los concilia contra un maestro Excel local,
genera un reporte Excel y deja auditoría y evidencias en Google
Sheets / Google Drive, con notificación por Gmail y un resumen por
webhook HTTP. El punto de entrada es `main.py`; los módulos están en
`src/`.

## Chatbot de soporte (`chatbot/`)

### Qué es

Un asistente de diagnóstico para errores del RPA. El usuario abre una
URL, describe el error en una interfaz de chat y recibe un diagnóstico
breve generado por Gemini: qué módulo lo originó, la causa probable y
un paso concreto para verificarlo o corregirlo. El modelo recibe un
contexto fijo (`CONTEXTO_RPA` en `chatbot/Code.gs`) con el flujo real
de `main.py`, las funciones clave, los selectores, los timeouts, los
reintentos y los mensajes de error exactos de cada módulo de `src/`.
Cada consulta queda registrada en la pestaña `bot-rpa` de la misma
Google Sheet de auditoría del RPA.

Está construido sobre Google Apps Script y es independiente del código
Python: no lo importa ni lo ejecuta.

| Archivo | Contenido |
|---|---|
| `chatbot/Code.gs` | Servidor: sirve la interfaz, consulta Gemini y registra en la Sheet |
| `chatbot/Interfaz.html` | Interfaz de chat |
| `chatbot/appsscript.json` | Manifiesto: Web App con acceso restringido al dominio |
| `chatbot/README.md` | Guía completa de configuración, despliegue y decisiones de diseño |

### Por qué Web App y no Google Chat App

La primera versión se hizo como app de Google Chat, pero el dominio
institucional (Google Workspace for Education de DuocUC) bloquea las
apps de Chat personalizadas desde la administración. Incluso un bot
mínimo de eco, en un proyecto nuevo y con la configuración de Cloud
Console verificada, nunca llegaba a ejecutar el script: cero
ejecuciones y cero logs. Una Web App de Apps Script es solo una página
HTML con una URL, así que no depende de la Google Chat API ni de sus
políticas de dominio.

### Configuración y despliegue (resumen)

1. Desde la Google Sheet de auditoría del RPA, abre Extensiones > Apps
   Script, para que el proyecto quede vinculado a esa Sheet.
2. Copia ahí `Code.gs`, `Interfaz.html` y `appsscript.json`.
3. En las Script Properties agrega `GEMINI_API_KEY`, generada en Google
   AI Studio con una cuenta **personal**. Las cuentas `@duocuc.cl`
   reciben un 403. `GEMINI_MODEL` es opcional.
4. Ve a Implementar > Nueva implementación > Aplicación web, con
   ejecución como tu cuenta y acceso para tu organización.
5. Después de cada cambio en el código, publica una **nueva versión**
   de la implementación existente. Si no lo haces, la URL `/exec` sigue
   sirviendo la versión anterior.

Si modificas mensajes de error, selectores o timeouts en `src/`,
actualiza también `CONTEXTO_RPA` para que el bot siga diagnosticando
con información vigente.

Detalle completo: [chatbot/README.md](chatbot/README.md).
