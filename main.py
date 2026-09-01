import time

from src.google_drive import GoogleDriveEvidencias
from src.google_sheets import GoogleSheetsAuditoria
from src.navegador import NavegadorTestFire

"""
Archivo principal del RPA Demo TestFire.

Por ahora, este programa realiza una prueba inicial:

1. Se conecta a Google Sheets.
2. Se conecta a Google Drive.
3. Genera un identificador único de ejecución.
4. Inicia Firefox.
5. Abre Demo TestFire.
6. Guarda una captura.
7. Sube la captura a Drive.
8. Registra el resultado en Google Sheets.
9. Cierra Firefox aunque ocurra un error.
"""



def main():
    """
    Coordina la ejecución principal del robot.

    Esta función no realiza directamente el trabajo técnico. Su función
    es crear los objetos necesarios y llamarlos en el orden correcto.
    """

    # Conectamos con la hoja donde se registrará la auditoría.
    auditoria = GoogleSheetsAuditoria()

    # Preparamos el servicio que subirá evidencias a Drive.
    drive = GoogleDriveEvidencias()

    # Creamos el objeto que controlará Firefox.
    # Firefox todavía no se abre en esta línea.
    navegador = NavegadorTestFire()

    # Cada ejecución obtiene un identificador irrepetible.
    id_ejecucion = auditoria.crear_id_ejecucion()

    # perf_counter es apropiado para medir duración de procesos.
    inicio = time.perf_counter()

    try:
        # Iniciamos Firefox.
        navegador.iniciar()

        # Abrimos TestFire y recibimos la captura y el título.
        ruta_captura, titulo = navegador.abrir_testfire(
            id_ejecucion
        )

        # Subimos la captura a la carpeta configurada en Drive.
        # El método devuelve el enlace del archivo subido.
        enlace_drive = drive.subir_archivo(
            ruta_captura,
            ruta_captura.name,
        )

        # Registramos el resultado exitoso en Google Sheets.
        auditoria.registrar_evento(
            id_ejecucion=id_ejecucion,
            modulo="Navegador",
            accion="Abrir Demo TestFire",
            estado="Exitoso",
            detalle=f"Página cargada. Título: {titulo}",
            tiempo_inicio=inicio,
            evidencia_drive=enlace_drive,
        )

        print(f"\nID de ejecución: {id_ejecucion}")

        # Esta pausa permite revisar visualmente el sitio.
        input("Presiona ENTER para cerrar Firefox...")

    except Exception as error:
        """
        Este bloque se ejecuta si ocurre cualquier excepción dentro
        del try, por ejemplo:

        - GeckoDriver no existe.
        - Firefox no inicia.
        - TestFire no responde.
        - La captura no puede guardarse.
        - Drive rechaza el archivo.
        """

        # Aunque el proceso falle, registramos el intento.
        auditoria.registrar_evento(
            id_ejecucion=id_ejecucion,
            modulo="Navegador",
            accion="Abrir Demo TestFire",
            estado="Fallido",
            detalle=str(error)[:300],
            tiempo_inicio=inicio,
        )

        # raise vuelve a lanzar la excepción para mostrar su detalle
        # completo en la terminal.
        raise

    finally:
        """
        finally siempre se ejecuta, independientemente de que el
        proceso haya terminado correctamente o con error.
        """

        # Garantiza que Firefox y GeckoDriver no queden abiertos.
        navegador.cerrar()


# Esta condición permite ejecutar main() solamente cuando iniciamos:
#
#     py main.py
#
# También evita que main se ejecute accidentalmente al importar
# este archivo desde las pruebas.
if __name__ == "__main__":
    main()