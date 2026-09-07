import json
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import InvalidSessionIdException, NoSuchWindowException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

"""
Módulo encargado de controlar Firefox mediante Selenium.

Responsabilidades:
- Leer la configuración general del proyecto.
- Iniciar Firefox mediante GeckoDriver.
- Abrir Demo TestFire.
- Esperar que la página cargue.
- Capturar una evidencia.
- Cerrar el navegador correctamente.
"""


class FirefoxCerradoError(RuntimeError):
    """La ventana o sesión de Firefox terminó antes de tiempo."""


class NavegadorTestFire:
    """
    Administra el navegador utilizado por el RPA.

    Una clase permite mantener juntos los datos y las funciones relacionadas
    con Firefox. El atributo principal es `driver`, que representa la ventana
    del navegador controlada por Selenium.
    """

    def __init__(self):
        """
        Constructor de la clase.

        Se ejecuta automáticamente cuando escribimos:

            navegador = NavegadorTestFire()

        En este punto:
        1. Se determina la carpeta principal del proyecto.
        2. Se carga config/config.json.
        3. Se inicializa driver con valor None porque Firefox todavía
           no ha sido abierto.
        """

        # __file__ corresponde a src/navegador.py.
        # parent corresponde a la carpeta src.
        # parent.parent corresponde a la raíz del proyecto.
        self.raiz_proyecto = Path(__file__).resolve().parent.parent

        # Guardamos en memoria la configuración del proyecto.
        self.configuracion = self._cargar_configuracion()

        # Todavía no existe una ventana de Firefox.
        self.driver = None

    def _cargar_configuracion(self):
        """
        Lee el archivo config/config.json.

        Returns:
            dict: Configuración convertida desde JSON a diccionario Python.

        Raises:
            FileNotFoundError: Si config.json no existe.
            json.JSONDecodeError: Si el JSON contiene errores de sintaxis.

        El guion bajo inicial indica que este método está pensado para
        utilizarse internamente dentro de la clase.
        """

        ruta_config = self.raiz_proyecto / "config" / "config.json"

        # Validamos la existencia del archivo antes de abrirlo.
        if not ruta_config.exists():
            raise FileNotFoundError(f"No se encontró config.json en: {ruta_config}")

        # encoding="utf-8" permite leer correctamente tildes y ñ.
        with open(ruta_config, "r", encoding="utf-8") as archivo:
            configuracion = json.load(archivo)

        return configuracion

    def iniciar(self):
        """
        Inicia Firefox utilizando GeckoDriver.

        Este método:
        1. Obtiene la ruta de GeckoDriver desde config.json.
        2. Comprueba que el ejecutable exista.
        3. Configura Firefox.
        4. Crea el objeto WebDriver.
        5. Maximiza la ventana.
        6. Establece un tiempo máximo de carga.

        Raises:
            FileNotFoundError: Si GeckoDriver no existe en la ruta indicada.
            WebDriverException: Si Firefox no puede iniciarse.
        """

        configuracion_testfire = self.configuracion["testfire"]

        # Path transforma la ruta escrita en config.json en una ruta
        # que Python puede comprobar y utilizar.
        ruta_geckodriver = Path(configuracion_testfire["geckodriver_path"])

        if not ruta_geckodriver.exists():
            raise FileNotFoundError(
                f"No se encontró GeckoDriver en: {ruta_geckodriver}"
            )

        # Options permite configurar el comportamiento de Firefox.
        opciones = Options()

        # Demo TestFire puede presentar advertencias de certificados.
        # Esta configuración permite continuar en el sitio de prueba.
        opciones.accept_insecure_certs = True

        # Service indica a Selenium dónde se encuentra GeckoDriver.
        servicio = Service(str(ruta_geckodriver))

        # Creamos la instancia real del navegador.
        self.driver = webdriver.Firefox(
            service=servicio,
            options=opciones,
        )

        # Abrimos Firefox maximizado para que los elementos sean visibles.
        self.driver.maximize_window()

        # Si una página demora más de 30 segundos, Selenium generará
        # una excepción en vez de esperar indefinidamente.
        self.driver.set_page_load_timeout(30)

        print("[SELENIUM] Firefox iniciado correctamente.")

    def abrir_testfire(self, id_ejecucion):
        """
        Abre Demo TestFire y guarda una captura de pantalla.

        Args:
            id_ejecucion (str): Identificador único de la ejecución actual.
                Se utiliza para que cada captura tenga un nombre diferente.

        Returns:
            tuple:
                - Path: Ruta local de la captura.
                - str: Título encontrado en la página.

        Raises:
            RuntimeError: Si Firefox no fue iniciado previamente.
            TimeoutException: Si el contenido de la página no aparece
                dentro del tiempo configurado.
        """

        # Evita intentar navegar sin haber ejecutado iniciar().
        if self.driver is None:
            raise RuntimeError("El navegador todavía no ha sido iniciado.")

        configuracion_testfire = self.configuracion["testfire"]

        url = configuracion_testfire["url"]
        timeout = configuracion_testfire["timeout_segundos"]

        print(f"[SELENIUM] Abriendo: {url}")

        # driver.get navega hacia la dirección indicada.
        self.driver.get(url)

        # Espera explícita:
        # Selenium esperará como máximo `timeout` segundos hasta encontrar
        # el elemento <body> de la página.
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Obtenemos el texto de la pestaña del navegador.
        titulo = self.driver.title.strip()

        # Obtenemos la carpeta de evidencias desde config.json.
        ruta_evidencias = self.raiz_proyecto / self.configuracion["rutas"]["evidencias"]

        # Si la carpeta no existe, se crea automáticamente.
        ruta_evidencias.mkdir(
            parents=True,
            exist_ok=True,
        )

        # El ID evita que una captura sobrescriba a otra.
        ruta_captura = ruta_evidencias / f"{id_ejecucion}_inicio_testfire.png"

        # save_screenshot devuelve True si la captura se guardó.
        captura_correcta = self.driver.save_screenshot(str(ruta_captura))

        if not captura_correcta:
            raise RuntimeError("Firefox no pudo guardar la captura.")

        print(f"[SELENIUM] Página cargada: {titulo}")
        print(f"[EVIDENCIA] Captura guardada: " f"{ruta_captura.name}")

        # Devolvemos dos resultados:
        # la ubicación de la captura y el título de la página.
        return ruta_captura, titulo

    def capturar_evidencia(self, id_ejecucion, nombre_paso):
        """
        Guarda una captura de la página actualmente visible.

        Este método podrá utilizarse en cualquier etapa del robot:
        login, resumen de cuentas, movimientos, conciliación o errores.

        Args:
            id_ejecucion (str):
                Identificador único de la ejecución actual.

            nombre_paso (str):
                Nombre descriptivo de la evidencia, por ejemplo:
                "login_exitoso" o "account_summary".

        Returns:
            Path:
                Ruta completa donde se guardó la captura.

        Raises:
            RuntimeError:
                Si Firefox no está iniciado o la captura no puede guardarse.
        """

        # No podemos capturar si Selenium todavía no creó Firefox.
        if self.driver is None:
            raise RuntimeError("No se puede capturar porque Firefox no está iniciado.")

        # Obtenemos la carpeta de evidencias desde config.json.
        ruta_evidencias = self.raiz_proyecto / self.configuracion["rutas"]["evidencias"]

        # Crea la carpeta solamente si todavía no existe.
        # exist_ok=True evita duplicarla o generar un error.
        ruta_evidencias.mkdir(
            parents=True,
            exist_ok=True,
        )

        # El ID de ejecución evita sobrescribir capturas anteriores.
        ruta_captura = ruta_evidencias / f"{id_ejecucion}_{nombre_paso}.png"

        # Selenium captura exactamente lo que muestra Firefox.
        captura_correcta = self.driver.save_screenshot(str(ruta_captura))

        # save_screenshot devuelve False si no pudo crear la imagen.
        if not captura_correcta:
            raise RuntimeError(f"No se pudo guardar la captura: {nombre_paso}")

        print(f"[EVIDENCIA] Captura guardada: " f"{ruta_captura.name}")

        return ruta_captura

    def verificar_abierto(self):
        """Comprueba la sesión entre etapas, sin abrir otra ventana."""
        if self.driver is None:
            return
        try:
            if not self.driver.window_handles:
                raise FirefoxCerradoError("Firefox se cerró antes de completar la ejecución.")
        except (InvalidSessionIdException, NoSuchWindowException) as error:
            raise FirefoxCerradoError(
                "Firefox se cerró antes de completar la ejecución."
            ) from error

    def cerrar(self):
        """
        Cierra Firefox y finaliza GeckoDriver.

        El método comprueba primero si el navegador existe. Esto evita
        errores cuando Firefox no alcanzó a iniciarse.
        """

        if self.driver is not None:
            # quit() cierra todas las ventanas y termina GeckoDriver.
            try:
                self.driver.quit()
            except (InvalidSessionIdException, NoSuchWindowException):
                pass

            # Restablecemos el atributo para indicar que ya no existe
            # una sesión activa.
            self.driver = None

            print("[SELENIUM] Navegador cerrado.")
