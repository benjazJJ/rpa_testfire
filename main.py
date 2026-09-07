"""
Archivo principal del RPA para Demo TestFire.

Flujo actual:

1. Solicitar las credenciales bancarias.
2. Conectar con Google Sheets y Google Drive.
3. Abrir Firefox.
4. Abrir Demo TestFire.
5. Guardar y subir una captura inicial.
6. Iniciar sesión automáticamente.
7. Guardar y subir la evidencia del login.
8. Abrir la sección de actividad de la cuenta.
9. Extraer los movimientos de la tabla.
10. Conciliar los movimientos con el archivo maestro local.
11. Generar un reporte Excel con movimientos y conciliación.
12. Subir el reporte Excel a Google Drive.
13. Enviar el reporte a los destinatarios mediante Gmail API.
14. Enviar un resumen JSON mediante HTTP POST.
15. Registrar cada acción en Google Sheets.
16. Mantener Firefox abierto hasta presionar ENTER.
17. Cerrar Firefox de manera segura.
"""

import getpass
import time
from selenium.common.exceptions import InvalidSessionIdException, NoSuchWindowException

from src.conciliacion import ConciliadorMovimientos
from src.excel_report import GeneradorReporteExcel
from src.google_drive import GoogleDriveEvidencias
from src.google_sheets import GoogleSheetsAuditoria
from src.logs import RegistroHttpWebhook
from src.navegador import FirefoxCerradoError, NavegadorTestFire
from src.notificaciones import NotificadorGmail
from src.testfire_bot import TestFireBot


def main():
    """
    Coordina todas las clases que participan en la automatización.

    Esta función controla el orden general del RPA. Las operaciones
    específicas del navegador, TestFire, Google Drive y Google Sheets
    se encuentran separadas en sus respectivas clases.
    """

    print("================================")
    print("RPA DEMO TESTFIRE")
    print("================================")

    # Si el usuario solamente presiona ENTER, se utiliza jsmith.
    usuario = (
        input("Usuario TestFire [jsmith]: ").strip()
        or "jsmith"
    )

    # getpass permite ingresar la contraseña sin mostrarla
    # visualmente en la consola.
    contrasena = getpass.getpass(
        "Contraseña TestFire: "
    )

    # Conexión con la Google Sheet utilizada para la auditoría.
    auditoria = GoogleSheetsAuditoria()

    # Conexión con la carpeta de evidencias en Google Drive.
    drive = GoogleDriveEvidencias()

    # Objeto encargado de iniciar, controlar y cerrar Firefox.
    navegador = NavegadorTestFire()

    # Identificador compartido por todos los eventos generados
    # durante esta ejecución.
    id_ejecucion = auditoria.crear_id_ejecucion()

    # Guarda el nombre del paso que se está ejecutando.
    # Si ocurre una excepción, permite identificar dónde falló.
    paso_actual = "Inicialización"

    # Valor inicial para evitar problemas si ocurre un error
    # antes de comenzar el primer paso.
    inicio_paso = time.perf_counter()

    # Estados iniciales utilizados en el resumen final.
    estado_login = "No ejecutado"
    estado_actividad = "No ejecutado"
    estado_extraccion = "No ejecutado"
    estado_conciliacion = "No ejecutado"
    estado_excel = "No ejecutado"
    estado_correo = "No ejecutado"
    estado_http = "No ejecutado"

    # Cantidad de movimientos obtenidos desde TestFire.
    cantidad_movimientos = 0
    movimientos = []
    robot = None
    ruta_reporte = None
    enlace_reporte = ""
    ultima_etapa = "Ninguna"
    proceso_terminado = False
    cierre_detectado = False

    # Valores iniciales de la conciliación. Se definen antes del
    # bloque try para poder mostrarlos de forma segura en el resumen.
    resultados_conciliacion = []
    resumen_conciliacion = {
        "conciliados": 0,
        "no_conciliados": 0,
    }

    def enviar_correo_final(estado_proceso, cantidad):
        """Notifica una sola vez, después de guardar el estado definitivo."""
        inicio_correo = time.perf_counter()
        try:
            notificador = NotificadorGmail()
            exito, detalle = notificador.enviar_reporte(
                destinatario=notificador.destinatarios_configurados,
                ruta_reporte=ruta_reporte,
                id_ejecucion=id_ejecucion,
                estado_conciliacion=estado_conciliacion,
                cantidad_movimientos=cantidad,
                enlace_drive=enlace_reporte,
                estado_proceso=estado_proceso,
            )
        except Exception as error_correo:
            exito = False
            detalle = (
                "No fue posible completar la notificación por correo. "
                f"Tipo de error: {type(error_correo).__name__}."
            )
            print(f"[GMAIL] {detalle}")
        estado = "Exitoso" if exito else "Fallido"
        try:
            auditoria.registrar_evento(
                id_ejecucion=id_ejecucion,
                modulo="Notificaciones",
                accion="Enviar reporte por correo",
                estado=estado,
                detalle=detalle,
                tiempo_inicio=inicio_correo,
                registros=cantidad,
                evidencia_drive=enlace_reporte,
            )
        except Exception as error_auditoria:
            print(f"[AUDITORÍA] No se pudo registrar el correo: {type(error_auditoria).__name__}.")
        return estado

    try:
        # PASO 1: ABRIR DEMO TESTFIRE

        navegador.verificar_abierto()
        ultima_etapa = paso_actual
        paso_actual = "Abrir Demo TestFire"
        inicio_paso = time.perf_counter()

        navegador.iniciar()

        # abrir_testfire devuelve:
        # - La ruta local de la captura.
        # - El título de la página.
        ruta_inicio, titulo = navegador.abrir_testfire(
            id_ejecucion
        )

        # Subimos la evidencia inicial a Google Drive.
        enlace_inicio = drive.subir_archivo(
            ruta_inicio,
            ruta_inicio.name,
        )

        # Registramos la apertura exitosa del sitio y guardamos
        # el enlace de su evidencia.
        auditoria.registrar_evento(
            id_ejecucion=id_ejecucion,
            modulo="Navegador",
            accion=paso_actual,
            estado="Exitoso",
            detalle=f"Página cargada. Título: {titulo}",
            tiempo_inicio=inicio_paso,
            evidencia_drive=enlace_inicio,
        )

        # PASO 2: INICIAR SESIÓN

        navegador.verificar_abierto()
        ultima_etapa = paso_actual
        paso_actual = "Iniciar sesión"
        # TestFireBot utiliza el mismo Firefox que fue iniciado
        # por NavegadorTestFire.
        robot = TestFireBot(navegador)

        # Repetimos el login hasta que TestFire acepte las credenciales.
        # Cada intento genera su propia evidencia y registro de auditoría.
        numero_intento = 0

        while True:
            navegador.verificar_abierto()
            # Una contraseña vacía no se envía al sitio.
            if not contrasena:
                print(
                    "\n[LOGIN] La contraseña no puede estar vacía. "
                    "Inténtalo nuevamente.\n"
                )
            else:
                numero_intento += 1
                inicio_paso = time.perf_counter()

                # Agregar el número de intento evita que una captura
                # sobrescriba la evidencia de un intento anterior.
                id_evidencia_login = (
                    f"{id_ejecucion}_intento_{numero_intento}"
                )

                (
                    exito_login,
                    ruta_login,
                    detalle_login,
                ) = robot.iniciar_sesion(
                    usuario=usuario,
                    contrasena=contrasena,
                    id_ejecucion=id_evidencia_login,
                )

                # Subimos y auditamos tanto los intentos exitosos como
                # los rechazados, sin almacenar nunca la contraseña.
                enlace_login = drive.subir_archivo(
                    ruta_login,
                    ruta_login.name,
                )

                estado_login = (
                    "Exitoso" if exito_login else "Fallido"
                )

                auditoria.registrar_evento(
                    id_ejecucion=id_ejecucion,
                    modulo="Autenticación",
                    accion=(
                        f"{paso_actual} - intento {numero_intento}"
                    ),
                    estado=estado_login,
                    detalle=detalle_login,
                    tiempo_inicio=inicio_paso,
                    evidencia_drive=enlace_login,
                )

                if exito_login:
                    break

                es_rechazo_credenciales = any(
                    mensaje in detalle_login.lower()
                    for mensaje in (
                        "credenciales incorrectas",
                        "login failed",
                        "username or password was not found",
                    )
                )

                print("\n================================")
                if es_rechazo_credenciales:
                    print("CREDENCIALES INCORRECTAS")
                    print("================================")
                    print("El usuario o la contraseña no son válidos.")
                else:
                    print("NO FUE POSIBLE INICIAR SESIÓN")
                    print("================================")
                    print(detalle_login)

                if numero_intento >= 3:
                    print("\n================================")
                    print("MÁXIMO DE INTENTOS ALCANZADO")
                    print("================================")
                    print(
                        "El RPA se cerrará por seguridad después "
                        "de tres intentos fallidos."
                    )
                    return

                print("Vuelve a intentarlo.\n")

            usuario = (
                input("Usuario TestFire [jsmith]: ").strip()
                or "jsmith"
            )
            contrasena = getpass.getpass(
                "Contraseña TestFire: "
            )

        # PASO 3: ABRIR ACTIVIDAD DE LA CUENTA

        # La actividad bancaria solamente puede consultarse
        # cuando el inicio de sesión fue exitoso.
        if exito_login:
            navegador.verificar_abierto()
            ultima_etapa = paso_actual
            paso_actual = "Abrir actividad de cuenta"
            inicio_paso = time.perf_counter()

            # El método abre View Recent Transactions y retorna:
            # - Resultado de la navegación.
            # - Ruta de la evidencia.
            # - Descripción del resultado.
            (
                exito_actividad,
                ruta_actividad,
                detalle_actividad,
            ) = robot.abrir_actividad_cuenta(
                id_ejecucion=id_ejecucion,
            )

            # Subimos a Google Drive la captura de la página
            # de movimientos.
            enlace_actividad = drive.subir_archivo(
                ruta_actividad,
                ruta_actividad.name,
            )

            if exito_actividad:
                estado_actividad = "Exitoso"
            else:
                estado_actividad = "Fallido"

            # Registramos el resultado de la navegación.
            auditoria.registrar_evento(
                id_ejecucion=id_ejecucion,
                modulo="Consulta bancaria",
                accion=paso_actual,
                estado=estado_actividad,
                detalle=detalle_actividad,
                tiempo_inicio=inicio_paso,
                evidencia_drive=enlace_actividad,
            )

            # PASO 4: EXTRAER MOVIMIENTOS

            # La extracción solamente se ejecuta si la página
            # de actividad fue cargada correctamente.
            if exito_actividad:
                navegador.verificar_abierto()
                ultima_etapa = paso_actual
                paso_actual = "Extraer movimientos"
                inicio_paso = time.perf_counter()

                # El método retorna:
                # - Resultado de la extracción.
                # - Lista de movimientos.
                # - Ruta de la captura.
                # - Descripción del resultado.
                (
                    exito_extraccion,
                    movimientos,
                    ruta_extraccion,
                    detalle_extraccion,
                ) = robot.extraer_movimientos(
                    id_ejecucion=id_ejecucion,
                )

                # Contamos los elementos extraídos mediante len().
                cantidad_movimientos = len(movimientos)

                # Subimos la captura de la tabla procesada.
                enlace_extraccion = drive.subir_archivo(
                    ruta_extraccion,
                    ruta_extraccion.name,
                )

                if exito_extraccion:
                    estado_extraccion = "Exitoso"
                else:
                    estado_extraccion = "Fallido"

                # Registramos el resultado y la cantidad de filas
                # extraídas en Google Sheets.
                auditoria.registrar_evento(
                    id_ejecucion=id_ejecucion,
                    modulo="Extracción web",
                    accion=paso_actual,
                    estado=estado_extraccion,
                    detalle=detalle_extraccion,
                    tiempo_inicio=inicio_paso,
                    registros=cantidad_movimientos,
                    evidencia_drive=enlace_extraccion,
                )

                # Los pasos posteriores solamente se ejecutan cuando
                # la extracción de movimientos fue exitosa.
                if exito_extraccion:
                    # PASO 5: CONCILIAR MOVIMIENTOS

                    navegador.verificar_abierto()
                    ultima_etapa = paso_actual
                    paso_actual = "Conciliar movimientos"
                    inicio_paso = time.perf_counter()

                    # El conciliador compara los movimientos obtenidos
                    # desde TestFire con data/entrada/
                    # conciliacion_master.xlsx.
                    conciliador = ConciliadorMovimientos()

                    (
                        resultados_conciliacion,
                        resumen_conciliacion,
                    ) = conciliador.conciliar(movimientos)

                    # Una conciliación puede ejecutarse correctamente y
                    # aun así encontrar diferencias de negocio. Por eso
                    # distinguimos "Con diferencias" de un error técnico.
                    if resumen_conciliacion["no_conciliados"] == 0:
                        estado_conciliacion = "Exitoso"
                    else:
                        estado_conciliacion = "Con diferencias"

                    detalle_conciliacion = (
                        "Conciliación completada. "
                        f"Conciliados: "
                        f"{resumen_conciliacion['conciliados']} | "
                        f"Con diferencias: "
                        f"{resumen_conciliacion['con_diferencias']} | "
                        f"Solo en TestFire: "
                        f"{resumen_conciliacion['solo_testfire']} | "
                        f"Solo en maestro: "
                        f"{resumen_conciliacion['solo_maestro']}"
                    )

                    # El evento deja evidencia numérica del resultado
                    # aun antes de generar y subir el reporte Excel.
                    auditoria.registrar_evento(
                        id_ejecucion=id_ejecucion,
                        modulo="Conciliación",
                        accion=paso_actual,
                        estado=estado_conciliacion,
                        detalle=detalle_conciliacion,
                        tiempo_inicio=inicio_paso,
                        registros=len(resultados_conciliacion),
                    )

                    # PASO 6: GENERAR REPORTE EXCEL

                    navegador.verificar_abierto()
                    ultima_etapa = paso_actual
                    paso_actual = "Generar reporte Excel"
                    inicio_paso = time.perf_counter()

                    # Creamos el generador encargado de transformar
                    # la lista de movimientos en un libro Excel.
                    generador_excel = GeneradorReporteExcel()

                    # El archivo se guarda localmente en data/salida.
                    ruta_reporte = generador_excel.generar_reporte(
                        estado_proceso="EN CURSO",
                        ultima_etapa=ultima_etapa,
                        movimientos=movimientos,
                        id_ejecucion=id_ejecucion,
                        resultados_conciliacion=(
                            resultados_conciliacion
                        ),
                        resumen_conciliacion=(
                            resumen_conciliacion
                        ),
                    )

                    # Subimos el mismo reporte a Google Drive para
                    # mantener una copia centralizada y auditable.
                    enlace_reporte = drive.subir_archivo(
                        ruta_reporte,
                        ruta_reporte.name,
                    )

                    estado_excel = "Exitoso"

                    # Registramos en Google Sheets el nombre del
                    # reporte, los registros incluidos y su enlace.
                    auditoria.registrar_evento(
                        id_ejecucion=id_ejecucion,
                        modulo="Reporte",
                        accion=paso_actual,
                        estado=estado_excel,
                        detalle=(
                            "Reporte Excel generado y subido "
                            f"correctamente: {ruta_reporte.name}"
                        ),
                        tiempo_inicio=inicio_paso,
                        registros=cantidad_movimientos,
                        evidencia_drive=enlace_reporte,
                    )

                    # PASO 8: ENVIAR RESUMEN MEDIANTE HTTP POST

                    navegador.verificar_abierto()
                    ultima_etapa = paso_actual
                    paso_actual = "Enviar resumen HTTP"
                    inicio_paso = time.perf_counter()

                    # RegistroHttpWebhook obtiene la URL desde
                    # config/config.json. El JSON no incluye usuario,
                    # contraseña ni credenciales de Google.
                    registro_http = RegistroHttpWebhook()

                    exito_http, detalle_http = (
                        registro_http.enviar_resumen(
                            id_ejecucion=id_ejecucion,
                            estados={
                                "login": estado_login,
                                "actividad_cuenta": estado_actividad,
                                "extraccion": estado_extraccion,
                                "conciliacion": estado_conciliacion,
                                "reporte_excel": estado_excel,
                                "correo": estado_correo,
                            },
                            metricas={
                                "movimientos_extraidos": (
                                    cantidad_movimientos
                                ),
                                "movimientos_maestro": (
                                    resumen_conciliacion[
                                        "total_maestro"
                                    ]
                                ),
                                "conciliados": (
                                    resumen_conciliacion[
                                        "conciliados"
                                    ]
                                ),
                                "no_conciliados": (
                                    resumen_conciliacion[
                                        "no_conciliados"
                                    ]
                                ),
                                "con_diferencias": (
                                    resumen_conciliacion[
                                        "con_diferencias"
                                    ]
                                ),
                                "solo_testfire": (
                                    resumen_conciliacion[
                                        "solo_testfire"
                                    ]
                                ),
                                "solo_maestro": (
                                    resumen_conciliacion[
                                        "solo_maestro"
                                    ]
                                ),
                            },
                            enlace_reporte=enlace_reporte,
                        )
                    )

                    estado_http = (
                        "Exitoso" if exito_http else "Fallido"
                    )

                    # Aunque el webhook no esté disponible, el método
                    # devuelve False en lugar de lanzar una excepción.
                    # Así podemos dejar constancia en la auditoría sin
                    # perder el reporte que ya fue generado y subido.
                    auditoria.registrar_evento(
                        id_ejecucion=id_ejecucion,
                        modulo="Integración HTTP",
                        accion=paso_actual,
                        estado=estado_http,
                        detalle=detalle_http,
                        tiempo_inicio=inicio_paso,
                        registros=cantidad_movimientos,
                        evidencia_drive=enlace_reporte,
                    )

                else:
                    # Evitamos generar un archivo vacío cuando la
                    # extracción no pudo completarse correctamente.
                    print(
                        "[RPA] Reporte Excel omitido porque "
                        "la extracción no fue exitosa."
                    )

            else:
                # No se intenta extraer información si la página
                # de actividad no pudo cargarse.
                print(
                    "[RPA] Extracción omitida porque la actividad "
                    "de la cuenta no fue cargada."
                )

        else:
            # Si el login fue rechazado, el RPA no intenta acceder
            # a operaciones que requieren autenticación.
            print(
                "[RPA] Actividad de cuenta y extracción omitidas "
                "porque el inicio de sesión no fue exitoso."
            )

        navegador.verificar_abierto()
        if ruta_reporte is not None:
            GeneradorReporteExcel().actualizar_estado(
                ruta_reporte, "COMPLETADO", "", paso_actual,
            )
            try:
                drive.actualizar_archivo(ruta_reporte)
            except Exception as error_drive:
                print(
                    "[DRIVE] El Excel local tiene el estado final, pero no se pudo "
                    "actualizar la copia de Drive. "
                    f"Tipo de error: {type(error_drive).__name__}."
                )
        proceso_terminado = True
        if ruta_reporte is not None:
            estado_correo = enviar_correo_final("COMPLETADO", cantidad_movimientos)

        # RESUMEN FINAL

        print("")
        print("================================")
        print("RESULTADO DE LA EJECUCIÓN")
        print("================================")
        print(f"ID de ejecución: {id_ejecucion}")
        print(f"Resultado del login: {estado_login}")
        print(f"Actividad de cuenta: {estado_actividad}")
        print(f"Extracción de movimientos: {estado_extraccion}")
        print(f"Movimientos encontrados: {cantidad_movimientos}")
        print(f"Conciliación: {estado_conciliacion}")
        print(
            "Movimientos conciliados: "
            f"{resumen_conciliacion['conciliados']}"
        )
        print(
            "Movimientos no conciliados: "
            f"{resumen_conciliacion['no_conciliados']}"
        )
        print(f"Reporte Excel: {estado_excel}")
        print(f"Envío por correo: {estado_correo}")
        print(f"Envío HTTP POST: {estado_http}")

        # Permite revisar visualmente la última página antes
        # de cerrar Firefox.
        input(
            "\nPresiona ENTER para cerrar Firefox..."
        )

    except Exception as error:
        cierre_detectado = isinstance(
            error, (FirefoxCerradoError, InvalidSessionIdException, NoSuchWindowException)
        )
        if not cierre_detectado and not proceso_terminado:
            try:
                navegador.verificar_abierto()
            except FirefoxCerradoError:
                cierre_detectado = True
            except Exception:
                pass  # Un error distinto no demuestra que Firefox se cerró.
        if cierre_detectado and not proceso_terminado:
            motivo = "Firefox se cerró antes de completar la ejecución."
            print("\nPROCESO NO TERMINADO")
            print(motivo)
            print(f"Etapa interrumpida: {paso_actual}")
            try:
                generador = GeneradorReporteExcel()
                if ruta_reporte is not None:
                    generador.actualizar_estado(
                        ruta_reporte, "INCOMPLETO", motivo, ultima_etapa,
                    )
                else:
                    avance = movimientos or (
                        robot.movimientos_extraidos if robot is not None else []
                    )
                    ruta_reporte = generador.generar_reporte(
                        movimientos=avance,
                        id_ejecucion=id_ejecucion,
                        resultados_conciliacion=resultados_conciliacion,
                        resumen_conciliacion=resumen_conciliacion,
                        estado_proceso="INCOMPLETO",
                        motivo=motivo,
                        ultima_etapa=ultima_etapa,
                    )
                print(f"Se guardó el avance disponible en el archivo Excel: {ruta_reporte}")
                try:
                    enlace_reporte = drive.actualizar_archivo(ruta_reporte)
                except Exception as error_drive:
                    print(
                        "[DRIVE] El aviso se guardó localmente, pero no se pudo "
                        "guardar en Drive. "
                        f"Tipo de error: {type(error_drive).__name__}."
                    )
            except Exception as error_excel:
                print(f"[EXCEL] No se pudo guardar el aviso: {error_excel}")
            else:
                cantidad_avance = len(movimientos or (
                    robot.movimientos_extraidos if robot is not None else []
                ))
                estado_correo = enviar_correo_final("INCOMPLETO", cantidad_avance)
            return

        # Este bloque captura errores técnicos que no hayan sido
        # controlados por las clases.
        auditoria.registrar_evento(
            id_ejecucion=id_ejecucion,
            modulo="Error",
            accion=paso_actual,
            estado="Error",
            detalle=str(error)[:300],
            tiempo_inicio=inicio_paso,
        )

        print("")
        print("================================")
        print("ERROR EN LA EJECUCIÓN")
        print("================================")
        print(f"Paso: {paso_actual}")
        print(f"Detalle: {error}")

        # Volvemos a lanzar la excepción para que Python muestre
        # la traza completa y facilite encontrar el problema.
        raise

    finally:
        # Este bloque siempre se ejecuta, tanto si el proceso
        # termina correctamente como si ocurre un error.
        try:
            navegador.cerrar()
        except Exception:
            if not cierre_detectado:
                raise


if __name__ == "__main__":
    main()
