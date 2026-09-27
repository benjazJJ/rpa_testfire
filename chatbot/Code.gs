/**
 * Chatbot de soporte del RPA Demo TestFire, servido como Web App de
 * Apps Script (no como Google Chat App: el dominio institucional
 * DuocUC bloquea apps de Chat personalizadas a nivel de administrador).
 *
 * Flujo:
 * 1. El usuario abre la URL de la Web App (Interfaz.html).
 * 2. Escribe una pregunta describiendo un error del RPA.
 * 3. El HTML llama a consultarBot() vía google.script.run.
 * 4. consultarBot() consulta Gemini con contexto fijo del RPA,
 *    registra el intercambio en la pestaña "bot-rpa" de la Google
 *    Sheet de auditoría, y devuelve la respuesta al navegador.
 *
 * Configuración requerida (Editor > Configuración del proyecto >
 * Propiedades de secuencia de comandos):
 * - GEMINI_API_KEY : API Key de Google AI Studio (usar una cuenta
 *   personal; la cuenta institucional @duocuc.cl devuelve 403
 *   "denied access" en generateContent).
 * - GEMINI_MODEL   : (opcional) nombre del modelo. Por defecto
 *   "gemini-3.6-flash".
 *
 * Importante: este script debe estar vinculado directamente a la
 * Google Sheet de auditoría (Extensiones > Apps Script desde la
 * propia Sheet), ya que registrarLog() usa
 * SpreadsheetApp.getActiveSpreadsheet().
 *
 * Al editar este archivo, los cambios NO se reflejan en la URL
 * pública (.../exec) hasta publicar una "Nueva versión" sobre la
 * implementación existente (Implementar > Gestionar
 * implementaciones > editar > Nueva versión). Solo las Script
 * Properties se leen en tiempo real sin necesidad de reimplementar.
 */

const NOMBRE_HOJA_LOG = 'bot-rpa';

const CABECERAS_LOG = [
  'Fecha/Hora',
  'Usuario',
  'Canal',
  'Pregunta',
  'Respuesta',
  'Modelo',
  'Duración (seg)',
  'Estado',
];

/**
 * Contexto fijo enviado al modelo en cada consulta, para que
 * responda según la arquitectura real del RPA en vez de dar
 * diagnósticos genéricos.
 */
const CONTEXTO_RPA = `
Eres un asistente de soporte técnico para el RPA "Demo TestFire",
un robot en Python (Selenium + Firefox/GeckoDriver) que automatiza
el sitio bancario de demostración Altoro Mutual (testfire.net).

FLUJO DE main.py (orden real; la variable paso_actual indica dónde falló):
0. Pide usuario (por defecto "jsmith") y contraseña por consola.
   Instancia GoogleSheetsAuditoria y GoogleDriveEvidencias ANTES de
   abrir Firefox: si fallan credenciales/config de Google, el RPA cae
   sin abrir el navegador. ID de ejecución: RPA_YYYYMMDD_HHMMSS_XXXXXX.
1. "Abrir Demo TestFire" -> NavegadorTestFire.iniciar() + abrir_testfire().
2. "Iniciar sesión" -> TestFireBot.iniciar_sesion(), en bucle.
3. "Abrir actividad de cuenta" -> abrir_actividad_cuenta().
4. "Extraer movimientos" -> extraer_movimientos().
5. "Conciliar movimientos" -> ConciliadorMovimientos.conciliar().
6. "Generar reporte Excel" -> GeneradorReporteExcel.generar_reporte()
   (estado "EN CURSO") + subida a Drive.
7. "Enviar resumen HTTP" -> RegistroHttpWebhook.enviar_resumen().
8. Actualiza el Excel a "COMPLETADO", lo resube a Drive y recién ahí
   envía el correo (NotificadorGmail). Por eso el JSON del webhook
   siempre muestra "correo": "No ejecutado"; no es un error.
Cada paso falla "suave" (devuelve False + captura) y los siguientes se
omiten con mensajes "[RPA] ... omitida porque ...". Excepciones no
controladas se registran en Sheets con Módulo "Error" (detalle
truncado a 300 caracteres), se imprime "ERROR EN LA EJECUCIÓN / Paso:
..." y se relanzan con traza completa.

navegador.py (NavegadorTestFire):
- Lee config/config.json; si falta: "No se encontró config.json en: ...".
- iniciar(): valida testfire.geckodriver_path ("No se encontró
  GeckoDriver en: ..."), accept_insecure_certs=True, maximiza,
  set_page_load_timeout(30). Un fallo de webdriver.Firefox() suele ser
  versión Firefox/GeckoDriver incompatible o Firefox no instalado.
- abrir_testfire(): driver.get(testfire.url), espera <body> con
  testfire.timeout_segundos, guarda {id}_inicio_testfire.png en
  rutas.evidencias. Errores: "El navegador todavía no ha sido
  iniciado.", "Firefox no pudo guardar la captura.".
- capturar_evidencia(): "No se pudo guardar la captura: <paso>".
- verificar_abierto() se llama antes de cada paso y lanza
  FirefoxCerradoError("Firefox se cerró antes de completar la
  ejecución.") si no hay ventanas o hay InvalidSessionIdException /
  NoSuchWindowException. main.py lo trata como "PROCESO NO TERMINADO":
  genera/actualiza el Excel con estado "INCOMPLETO" y hoja de estado,
  lo sube a Drive y envía correo INCOMPLETO. No es un bug: el usuario
  cerró Firefox o el driver murió.

testfire_bot.py (TestFireBot, WebDriverWait de 15 s):
- iniciar_sesion(): si #uid no está visible hace click en #LoginLink;
  espera #uid y #passw, envía con [name=btnSubmit]. Éxito si la URL
  contiene /bank/main.jsp, o #LoginLink visible dice "Sign Off", o un
  h1/h2/h3 dice "Account Summary". Rechazo si hay texto visible "Login
  Failed" o "username or password was not found".
  Detalles devueltos (y capturas):
  * "Credenciales incorrectas: el usuario o la contraseña no fueron
    encontrados en el sistema." (login_fallido.png)
  * "Tiempo de espera agotado: no fue posible determinar el resultado
    del inicio de sesión." (login_sin_resultado.png): sitio lento o
    cambió el HTML.
  * "TestFire respondió, pero el resultado del inicio de sesión no pudo
    determinarse." (login_indeterminado.png): selectores de éxito/error
    desactualizados.
  Reintentos (main.py): máximo 3 intentos; contraseña vacía no cuenta
  como intento y no se envía. Al 3er fallo imprime "MÁXIMO DE INTENTOS
  ALCANZADO" y termina (return, sin Excel ni correo). Evidencias con
  sufijo _intento_N. ValueError si usuario/contraseña vacíos.
- abrir_actividad_cuenta(): click en #MenuHyperLink2, espera URL
  /bank/transaction.jsp, h1 "Recent Transactions" y la tabla
  #_ctl0__ctl0_Content_Main_MyTransactions. Errores: "No se puede abrir
  la actividad de la cuenta porque no existe una sesión iniciada." y
  "Tiempo de espera agotado al abrir la actividad de la cuenta.".
- extraer_movimientos(): lee filas .//tr[td] de esa tabla; ignora filas
  con < 5 celdas, la cabecera "Transaction ID" y filas vacías. Campos:
  id_transaccion, fecha_hora, id_cuenta, accion, monto. Errores: "No se
  pueden extraer movimientos porque el navegador no está en Recent
  Transactions." y "Tiempo de espera agotado: no se encontró la tabla
  de movimientos.". 0 filas NO es error de extracción, pero luego la
  conciliación lanza "No se recibieron movimientos de TestFire para
  conciliar.".

conciliacion.py (ConciliadorMovimientos):
- Maestro: data/entrada/conciliacion_master.xlsx, hoja "Movimientos"
  (o la activa). Columnas obligatorias exactas: ID Transacción,
  Fecha/Hora, ID Cuenta, Acción, Monto.
- Errores que lanza (ValueError/FileNotFoundError, detienen el RPA):
  "No se encontró el archivo maestro en: ...", "El archivo maestro no
  contiene las columnas: ...", "El archivo maestro contiene el ID
  duplicado 'X' en la fila N.", "El archivo conciliacion_master.xlsx no
  contiene movimientos.", "Los movimientos extraídos contienen el ID
  duplicado 'X'.", "Se encontró un movimiento sin ID de transacción.",
  "Se encontró un movimiento sin monto.", "El monto 'X' no tiene un
  formato válido.".
- Cruce por ID de transacción (quita ".0" final de IDs numéricos de
  Excel). Compara Fecha/Hora (normalizada a YYYY-MM-DD HH:MM, acepta
  %Y-%m-%d o %d-%m-%Y con/sin segundos), ID Cuenta, Acción
  (casefold) y Monto (Decimal; "$", "(x)" negativo, separadores , y .).
- Estados: "Conciliado", "Con diferencias" ("Campos diferentes: ..."),
  "Solo en TestFire" ("El ID no existe en el archivo maestro."), "Solo
  en maestro" ("El ID del maestro no fue encontrado en TestFire.").
  Si no_conciliados > 0 el paso queda "Con diferencias" (resultado de
  negocio, no error técnico). Muchos "Solo en ..." a la vez suelen
  indicar IDs con formato distinto o un maestro desactualizado.

excel_report.py (GeneradorReporteExcel): guarda
data/salida/movimientos_<id>.xlsx con hojas Movimientos, Resumen,
Conciliación y estado. Exige fecha EXACTA "%Y-%m-%d %H:%M": si no,
"La fecha recibida desde TestFire no tiene un formato válido: ..."
(envuelto en "Error al preparar el movimiento N: ..."). También "El
monto recibido desde TestFire no puede convertirse a número: ...".

google_sheets.py (GoogleSheetsAuditoria, service account
google.credenciales_path, spreadsheet_id, worksheet_name): exige 12
encabezados exactos (Fecha/Hora, ID Ejecución, PC, SO, Módulo,
Acción/Paso, Estado, Detalle, Duración (seg), Hora Término, Registros,
Evidencia Drive) o lanza "Los encabezados existentes no coinciden con
los encabezados requeridos por el RPA.". registrar_evento() nunca
lanza: imprime "[ERROR SHEETS] No se pudo registrar el evento: ...".
Si hay 403 / SpreadsheetNotFound: la Sheet no está compartida con el
correo de la service account.

google_drive.py (GoogleDriveEvidencias, OAuth de usuario:
oauth_drive_path + token_drive_path, carpeta drive_folder_id): "No se
encontró oauth_drive.json en: ...", "No se encontró el archivo: ...".
Token vencido/revocado -> borrar el token para reautorizar en el
navegador. Un fallo al subir SÍ detiene el RPA (no está en try).

notificaciones.py (NotificadorGmail, scope gmail.send, config
google.correo_remitente, google.correos_destinatarios, token por
defecto config/token_gmail.json): "No se encontró el archivo OAuth para
Gmail: ...", "Debe indicarse al menos un correo destinatario.", "La
dirección de correo destinataria no es válida.". HttpError ->
"No fue posible enviar el correo mediante Gmail API. Código HTTP: N.
Motivo: ...". Nunca detiene el RPA; solo marca "Envío por correo:
Fallido". Solo se envía si existe el reporte Excel.

logs.py (RegistroHttpWebhook, timeout 15 s, raise_for_status):
config webhook_url. Errores de config: "Falta configurar 'webhook_url'
en config/config.json.", "La propiedad 'webhook_url' no contiene una
URL HTTP/HTTPS válida.", "config/config.json no contiene un JSON
válido.". Fallo de red o HTTP 4xx/5xx -> "No fue posible completar el
HTTP POST. Tipo de error: <ConnectionError|Timeout|HTTPError>." (no
detiene el RPA).

Cuando alguien te describa un error o síntoma, responde en este orden:
1. Qué módulo/función probablemente lo originó.
2. La causa más probable (cita el mensaje o selector exacto si aplica).
3. Un paso concreto para verificarlo o corregirlo.

Sé muy breve, técnico y en español: máximo 4 líneas en total, sin
introducciones ni despedidas. Si no tienes información suficiente,
pide el mensaje de error exacto o el paso donde ocurrió, en una
sola línea.
`.trim();

/**
 * Sirve la página HTML cuando alguien abre la URL de la Web App.
 */
function doGet() {
  return HtmlService.createHtmlOutputFromFile('Interfaz')
    .setTitle('Asistente RPA TestFire')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/**
 * Punto de entrada llamado desde Interfaz.html vía google.script.run.
 * Consulta Gemini, registra el intercambio y devuelve la respuesta.
 */
function consultarBot(pregunta) {
  const inicio = Date.now();
  const usuario = obtenerCorreoUsuarioActual();

  let respuestaTexto;
  let estado = 'Exitoso';

  try {
    respuestaTexto = consultarGemini(pregunta);
  } catch (error) {
    estado = 'Fallido';
    respuestaTexto =
      'No pude consultar el modelo en este momento. Detalle técnico: ' + error.message;
  }

  const duracionSegundos = ((Date.now() - inicio) / 1000).toFixed(2);

  registrarLog({
    usuario,
    canal: 'Web App',
    pregunta,
    respuesta: respuestaTexto,
    modelo: obtenerModelo(),
    duracion: duracionSegundos,
    estado,
  });

  return respuestaTexto;
}

function obtenerCorreoUsuarioActual() {
  try {
    const correo = Session.getActiveUser().getEmail();
    return correo || 'Desconocido';
  } catch (error) {
    return 'Desconocido';
  }
}

/**
 * Llama a la API de Gemini (Generative Language API) combinando el
 * contexto fijo del RPA con la pregunta del usuario.
 *
 * thinkingConfig.thinkingBudget: 0 intenta desactivar el razonamiento
 * interno del modelo (no confirmado si tiene efecto en gemini-3.6-flash
 * vía esta API); la brevedad se fuerza principalmente por instrucción
 * en CONTEXTO_RPA, que es lo que realmente controla la longitud de la
 * respuesta.
 */
function consultarGemini(pregunta) {
  const apiKey = obtenerPropiedad('GEMINI_API_KEY');
  const modelo = obtenerModelo();

  const url =
    'https://generativelanguage.googleapis.com/v1beta/models/' +
    modelo +
    ':generateContent?key=' +
    apiKey;

  const payload = {
    system_instruction: {
      parts: [{ text: CONTEXTO_RPA }],
    },
    contents: [
      {
        role: 'user',
        parts: [{ text: pregunta }],
      },
    ],
    generationConfig: {
      maxOutputTokens: 4096,
      thinkingConfig: {
        thinkingBudget: 0,
      },
    },
  };

  const opciones = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  };

  const respuesta = UrlFetchApp.fetch(url, opciones);
  const codigo = respuesta.getResponseCode();
  const cuerpo = JSON.parse(respuesta.getContentText());

  if (codigo !== 200) {
    const motivo = (cuerpo.error && cuerpo.error.message) || ('HTTP ' + codigo);
    throw new Error(motivo);
  }

  const candidato = cuerpo.candidates && cuerpo.candidates[0];
  const texto =
    candidato &&
    candidato.content &&
    candidato.content.parts &&
    candidato.content.parts[0] &&
    candidato.content.parts[0].text;

  if (!texto) {
    throw new Error('La API no devolvió contenido utilizable.');
  }

  return texto.trim();
}

/**
 * Agrega una fila con la conversación a la pestaña "bot-rpa" de
 * esta misma Sheet. Crea la pestaña y sus encabezados si todavía
 * no existen.
 */
function registrarLog(datos) {
  const hoja = obtenerOCrearHojaLog();

  hoja.appendRow([
    new Date(),
    datos.usuario,
    datos.canal,
    datos.pregunta,
    datos.respuesta,
    datos.modelo,
    datos.duracion,
    datos.estado,
  ]);
}

function obtenerOCrearHojaLog() {
  const libro = SpreadsheetApp.getActiveSpreadsheet();

  let hoja = libro.getSheetByName(NOMBRE_HOJA_LOG);

  if (!hoja) {
    hoja = libro.insertSheet(NOMBRE_HOJA_LOG);
    hoja.appendRow(CABECERAS_LOG);
    hoja.setFrozenRows(1);
  }

  return hoja;
}

function obtenerModelo() {
  return obtenerPropiedad('GEMINI_MODEL', 'gemini-3.6-flash');
}

/**
 * Lee una Script Property obligatoria (o con valor por defecto).
 * Evita hardcodear API keys en el código fuente, que quedaría
 * expuesto si el proyecto de Apps Script se comparte.
 */
function obtenerPropiedad(nombre, valorPorDefecto) {
  const valor = PropertiesService.getScriptProperties().getProperty(nombre);

  if (valor) {
    return valor;
  }

  if (valorPorDefecto !== undefined) {
    return valorPorDefecto;
  }

  throw new Error("Falta configurar la Script Property '" + nombre + "'.");
}
