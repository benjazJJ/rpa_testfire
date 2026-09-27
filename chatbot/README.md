# Chatbot de soporte RPA Demo TestFire (Web App + Apps Script + Gemini)

Herramienta manual: un usuario abre una URL, describe un error del
RPA en una interfaz de chat, y recibe un diagnóstico generado por
Gemini con contexto real de los módulos del RPA. Cada intercambio
queda registrado en la pestaña `bot-rpa` de la Google Sheet de
auditoría del RPA.

## Por qué Web App y no Google Chat

La primera versión se construyó como una app de Google Chat, pero
el dominio institucional (Google Workspace for Education de DuocUC)
bloquea a nivel de administrador las apps de Chat personalizadas: ni
siquiera un bot mínimo de eco, en un proyecto nuevo y con toda la
configuración de Cloud Console verificada paso a paso, llegaba a
ejecutar el script (cero ejecuciones, cero logs, en cualquier punto
de la cadena). Una Web App de Apps Script evita esa capa por
completo: es solo una página HTML con una URL, sin pasar por la
Google Chat API ni sus políticas de administrador de dominio.

## Archivos

- `Code.gs` — lógica del servidor: sirve la interfaz (`doGet`),
  consulta Gemini (`consultarGemini`), registra cada intercambio en
  la Sheet (`registrarLog`).
- `Interfaz.html` — interfaz de chat (burbujas de conversación,
  indicador de "escribiendo", botón de copiar, preguntas de ejemplo).
- `appsscript.json` — manifiesto: despliegue como Web App, ejecuta
  con los permisos de quien la implementó, acceso restringido al
  dominio DuocUC.

## Configuración

1. Abre la Google Sheet de auditoría del RPA > Extensiones > Apps
   Script. Esto vincula el proyecto directamente a esa Sheet (no
   hace falta pasar el ID de la planilla por configuración aparte,
   `registrarLog` usa `SpreadsheetApp.getActiveSpreadsheet()`).
2. Reemplaza `Código.gs`, `appsscript.json` y crea `Interfaz.html`
   (Ver > Mostrar manifiesto para editar el `.json`) con el
   contenido de este paquete.
3. Configuración del proyecto > Propiedades de secuencia de
   comandos > agrega `GEMINI_API_KEY`.
   **Importante:** genera esta key en [Google AI Studio](https://aistudio.google.com/apikey)
   con una cuenta de Gmail **personal**, no institucional — la
   cuenta `@duocuc.cl` devuelve `403: Your project has been denied
   access` en `generateContent`, muy probablemente por una
   restricción de Google Workspace for Education sobre la
   Generative Language API.
4. `GEMINI_MODEL` es opcional (por defecto `gemini-3.6-flash`).

## Desplegar

1. Implementar > Nueva implementación > tipo **Aplicación web**.
2. Ejecutar como: tu cuenta. Quién tiene acceso: tu organización
   (DuocUC) — coincide con `access: "DOMAIN"` del manifiesto.
3. Autoriza los permisos solicitados (Sheets + conexiones externas)
   la primera vez.
4. Copia la URL `.../macros/s/AKfycb.../exec` y ábrela.

**Crítico:** después de CUALQUIER cambio en `Código.gs` o
`Interfaz.html`, la URL pública no refleja el cambio hasta publicar
una **nueva versión** sobre la implementación existente
(Implementar > Gestionar implementaciones > editar la implementación
tipo Aplicación web > cambiar "Versión" a "Nueva versión" >
Implementar). Solo las Script Properties se leen en tiempo real sin
este paso.

## Decisiones de diseño relevantes

- **Prompt breve por instrucción, no por límite de tokens.** Se
  intentó controlar la longitud de la respuesta con
  `generationConfig.thinkingConfig.thinkingBudget: 0` para desactivar
  el razonamiento interno de `gemini-3.6-flash`, pero no hay
  confirmación de que tenga efecto en esta API todavía. Lo que
  realmente controla la brevedad es la instrucción explícita en
  `CONTEXTO_RPA` ("máximo 4 líneas..."). `maxOutputTokens: 4096`
  queda como red de seguridad amplia, no como mecanismo de control.
- **`Session.getActiveUser().getEmail()` envuelto en try/catch** —
  no siempre está disponible según el contexto de ejecución de la
  Web App; si falla, se registra "Desconocido" en vez de romper la
  consulta.
- **Sin scopes de Chat/Gmail**: al ser una Web App simple, el
  manifiesto no declara `oauthScopes` explícitos — Apps Script los
  infiere de las llamadas reales del código (Sheets, `UrlFetchApp`).
