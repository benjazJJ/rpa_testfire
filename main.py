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
10. Generar un reporte Excel con los movimientos.
11. Subir el reporte Excel a Google Drive.
12. Registrar cada acción en Google Sheets.
13. Mantener Firefox abierto hasta presionar ENTER.
14. Cerrar Firefox de manera segura.
"""

import getpass
import time

from src.excel_report import GeneradorReporteExcel
from src.google_drive import GoogleDriveEvidencias
from src.google_sheets import GoogleSheetsAuditoria
from src.navegador import NavegadorTestFire
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
    estado_excel = "No ejecutado"

    # Cantidad de movimientos obtenidos desde TestFire.
    cantidad_movimientos = 0

    try:
        # PASO 1: ABRIR DEMO TESTFIRE

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

        paso_actual = "Iniciar sesión"
        inicio_paso = time.perf_counter()

        # TestFireBot utiliza el mismo Firefox que fue iniciado
        # por NavegadorTestFire.
        robot = TestFireBot(navegador)

        # El método retorna:
        # - True o False según el resultado.
        # - La ruta local de la captura.
        # - Una descripción del resultado.
        (
            exito_login,
            ruta_login,
            detalle_login,
        ) = robot.iniciar_sesion(
            usuario=usuario,
            contrasena=contrasena,
            id_ejecucion=id_ejecucion,
        )

        # Subimos la captura del resultado del login.
        enlace_login = drive.subir_archivo(
            ruta_login,
            ruta_login.name,
        )

        # Transformamos el valor booleano en un estado legible.
        if exito_login:
            estado_login = "Exitoso"
        else:
            estado_login = "Fallido"

        # Registramos el resultado del login en Google Sheets.
        auditoria.registrar_evento(
            id_ejecucion=id_ejecucion,
            modulo="Autenticación",
            accion=paso_actual,
            estado=estado_login,
            detalle=detalle_login,
            tiempo_inicio=inicio_paso,
            evidencia_drive=enlace_login,
        )

        # PASO 3: ABRIR ACTIVIDAD DE LA CUENTA

        # La actividad bancaria solamente puede consultarse
        # cuando el inicio de sesión fue exitoso.
        if exito_login:
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

                # PASO 5: GENERAR REPORTE EXCEL

                # El reporte solamente se genera cuando la
                # extracción de movimientos fue exitosa.
                if exito_extraccion:
                    paso_actual = "Generar reporte Excel"
                    inicio_paso = time.perf_counter()

                    # Creamos el generador encargado de transformar
                    # la lista de movimientos en un libro Excel.
                    generador_excel = GeneradorReporteExcel()

                    # El archivo se guarda localmente en data/salida.
                    ruta_reporte = generador_excel.generar_reporte(
                        movimientos=movimientos,
                        id_ejecucion=id_ejecucion,
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
        print(f"Reporte Excel: {estado_excel}")

        # Permite revisar visualmente la última página antes
        # de cerrar Firefox.
        input(
            "\nPresiona ENTER para cerrar Firefox..."
        )

    except Exception as error:
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
        navegador.cerrar()


if __name__ == "__main__":
    main()
