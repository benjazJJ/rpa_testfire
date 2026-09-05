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
9. Guardar y subir la evidencia de los movimientos.
10. Registrar cada acción en Google Sheets.
11. Mantener Firefox abierto hasta presionar ENTER.
12. Cerrar Firefox de manera segura.
"""

import getpass
import time

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

        # Registramos la apertura exitosa del sitio.
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

        # Este paso solamente se ejecuta cuando el login fue
        # realmente exitoso.
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

            # Subimos a Drive la captura de la página
            # de movimientos.
            enlace_actividad = drive.subir_archivo(
                ruta_actividad,
                ruta_actividad.name,
            )

            # Convertimos el resultado booleano en texto.
            if exito_actividad:
                estado_actividad = "Exitoso"
            else:
                estado_actividad = "Fallido"

            # Registramos la navegación en Google Sheets.
            auditoria.registrar_evento(
                id_ejecucion=id_ejecucion,
                modulo="Consulta bancaria",
                accion=paso_actual,
                estado=estado_actividad,
                detalle=detalle_actividad,
                tiempo_inicio=inicio_paso,
                evidencia_drive=enlace_actividad,
            )

        else:
            # Si el login fue rechazado, el RPA no intenta acceder
            # a información que requiere una sesión autenticada.
            print(
                "[RPA] Actividad de cuenta omitida porque "
                "el inicio de sesión no fue exitoso."
            )

        # RESUMEN FINAL

        print("")
        print("================================")
        print("RESULTADO DE LA EJECUCIÓN")
        print("================================")
        print(f"ID de ejecución: {id_ejecucion}")
        print(f"Resultado del login: {estado_login}")
        print(
            f"Actividad de cuenta: {estado_actividad}"
        )

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