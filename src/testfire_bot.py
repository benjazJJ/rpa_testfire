"""
Automatización de las operaciones realizadas en Demo TestFire.

Esta clase contiene las acciones específicas del sitio Altoro Mutual.
La apertura y cierre de Firefox continúan siendo responsabilidad de la
clase NavegadorTestFire.
"""

from pathlib import Path

from selenium.common.exceptions import (
    TimeoutException,
    UnexpectedAlertPresentException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TestFireBot:
    """
    Robot encargado de interactuar con Demo TestFire.

    La clase recibe una instancia de NavegadorTestFire para reutilizar:

    - El controlador de Selenium.
    - La captura de evidencias.
    - La misma sesión de Firefox durante toda la ejecución.
    """

    def __init__(self, navegador, tiempo_espera: int = 15):
        """
        Inicializa el robot de Demo TestFire.

        Args:
            navegador:
                Instancia de NavegadorTestFire que contiene el driver
                de Selenium.

            tiempo_espera:
                Cantidad máxima de segundos que Selenium esperará por
                los elementos o resultados de la página.
        """

        self.navegador = navegador
        self.movimientos_extraidos = []
        self.driver = navegador.driver
        self.tiempo_espera = tiempo_espera

        # WebDriverWait permite esperar condiciones reales de la página,
        # evitando depender de pausas fijas como time.sleep().
        self.espera = WebDriverWait(
            self.driver,
            self.tiempo_espera,
        )

    def _login_exitoso(self) -> bool:
        """
        Comprueba si TestFire realmente inició una sesión.

        No se utiliza solamente la existencia de AccountLink porque ese
        elemento puede aparecer incluso cuando el usuario no ha iniciado
        sesión.

        El login se considera exitoso cuando se encuentra al menos una
        de las siguientes señales:

        1. La URL corresponde al módulo bancario principal.
        2. Aparece el enlace "Sign Off".
        3. Aparece el encabezado "Account Summary".

        Returns:
            bool:
                True si se detectó una sesión autenticada.
                False si no existen señales suficientes.
        """

        # Convertimos la URL a minúsculas para compararla sin depender
        # del uso de letras mayúsculas o minúsculas.
        url_actual = self.driver.current_url.lower()

        # Después de un login exitoso, TestFire normalmente redirige
        # al usuario hacia esta página.
        if "/bank/main.jsp" in url_actual:
            return True

        # LoginLink cambia su texto desde "Sign In" a "Sign Off"
        # únicamente cuando existe una sesión autenticada.
        enlaces_cerrar_sesion = self.driver.find_elements(
            By.XPATH,
            (
                "//a[@id='LoginLink' and contains("
                "translate(normalize-space(.), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                "'abcdefghijklmnopqrstuvwxyz'), "
                "'sign off')]"
            ),
        )

        for enlace in enlaces_cerrar_sesion:
            if enlace.is_displayed():
                return True

        # También comprobamos la aparición del encabezado de resumen
        # de cuentas, característico de la página posterior al login.
        encabezados_cuenta = self.driver.find_elements(
            By.XPATH,
            (
                "//*[self::h1 or self::h2 or self::h3]"
                "[contains("
                "translate(normalize-space(.), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                "'abcdefghijklmnopqrstuvwxyz'), "
                "'account summary')]"
            ),
        )

        for encabezado in encabezados_cuenta:
            if encabezado.is_displayed():
                return True

        return False

    def _obtener_error_login(self) -> str:
        """
        Obtiene el mensaje de rechazo mostrado por TestFire.

        Se buscan mensajes que contengan las expresiones utilizadas
        por el sitio cuando las credenciales son incorrectas.

        Si varios elementos contienen el mensaje, se selecciona el texto
        más corto. Esto evita devolver accidentalmente todo el contenido
        visible de la página.

        Returns:
            str:
                Mensaje de error encontrado.

                Retorna una cadena vacía cuando no existe un mensaje
                visible de rechazo.
        """

        elementos_error = self.driver.find_elements(
            By.XPATH,
            (
                "//*[contains("
                "translate(normalize-space(.), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                "'abcdefghijklmnopqrstuvwxyz'), "
                "'login failed') "
                "or contains("
                "translate(normalize-space(.), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                "'abcdefghijklmnopqrstuvwxyz'), "
                "'username or password was not found')]"
            ),
        )

        mensajes_visibles = []

        for elemento in elementos_error:
            if not elemento.is_displayed():
                continue

            # Eliminamos saltos de línea y espacios repetidos para
            # almacenar un detalle limpio en Google Sheets.
            mensaje = " ".join(elemento.text.split())

            if mensaje:
                mensajes_visibles.append(mensaje)

        if not mensajes_visibles:
            return ""

        # Los elementos padres también pueden contener el mensaje junto
        # al resto de la página. El texto más corto suele corresponder
        # exactamente al mensaje de error.
        mensaje_error = min(
            mensajes_visibles,
            key=len,
        )

        # Limitamos el largo para no ingresar textos excesivos
        # en la auditoría de Google Sheets.
        return mensaje_error[:500]

    def _esperar_resultado_login(self) -> None:
        """
        Espera hasta que TestFire informe el resultado del login.

        La condición termina cuando aparece:

        - Un mensaje de credenciales rechazadas; o
        - Una señal comprobable de sesión iniciada.

        Raises:
            TimeoutException:
                Cuando TestFire no entrega un resultado reconocible
                dentro del tiempo configurado.
        """

        # Firefox o el sitio pueden mostrar una alerta tras enviar el
        # formulario. Selenium la descarta automáticamente y lanza
        # UnexpectedAlertPresentException; en ese caso volvemos a esperar.
        for intento in range(3):
            try:
                self.espera.until(
                    lambda driver: (
                        bool(self._obtener_error_login())
                        or self._login_exitoso()
                    )
                )
                return

            except UnexpectedAlertPresentException as alerta:
                print(
                    "[TESTFIRE] Alerta descartada durante el login: "
                    f"{alerta.alert_text}"
                )

        raise TimeoutException(
            "Se repitieron alertas y no se obtuvo el resultado del login."
        )

    def iniciar_sesion(
        self,
        usuario: str,
        contrasena: str,
        id_ejecucion: str,
    ) -> tuple[bool, Path, str]:
        """
        Inicia sesión en Demo TestFire y genera una evidencia.

        El método realiza las siguientes acciones:

        1. Abre el formulario de inicio de sesión.
        2. Ingresa el usuario y la contraseña.
        3. Presiona el botón Login.
        4. Espera la respuesta del sitio.
        5. Comprueba primero si existe un mensaje de error.
        6. Captura una evidencia del resultado.

        Args:
            usuario:
                Nombre de usuario ingresado desde la consola.

            contrasena:
                Contraseña ingresada desde la consola.

            id_ejecucion:
                Identificador único de la ejecución actual del RPA.

        Returns:
            tuple[bool, Path, str]:
                Una tupla que contiene:

                - True o False según el resultado.
                - Ruta local de la captura de pantalla.
                - Descripción del resultado.

        Raises:
            ValueError:
                Cuando el usuario o la contraseña están vacíos.
        """

        # No permitimos enviar un formulario sin usuario.
        if not usuario.strip():
            raise ValueError(
                "El nombre de usuario no puede estar vacío."
            )

        # No mostramos ni incluimos la contraseña en mensajes,
        # capturas, logs o Google Sheets.
        if not contrasena:
            raise ValueError(
                "La contraseña no puede estar vacía."
            )

        print("[TESTFIRE] Abriendo formulario de inicio de sesión...")

        # Comprobamos si el formulario ya está visible. Esto permite
        # reutilizar el método aunque el navegador ya esté en login.jsp.
        campos_usuario_visibles = self.driver.find_elements(
            By.ID,
            "uid",
        )

        formulario_visible = any(
            campo.is_displayed()
            for campo in campos_usuario_visibles
        )

        if not formulario_visible:
            # Esperamos hasta que el enlace Sign In pueda presionarse.
            enlace_login = self.espera.until(
                EC.element_to_be_clickable(
                    (By.ID, "LoginLink")
                )
            )

            enlace_login.click()

        # Esperamos que el campo de usuario esté visible.
        campo_usuario = self.espera.until(
            EC.visibility_of_element_located(
                (By.ID, "uid")
            )
        )

        # Esperamos que el campo de contraseña esté visible.
        campo_contrasena = self.espera.until(
            EC.visibility_of_element_located(
                (By.ID, "passw")
            )
        )

        # Limpiamos ambos campos para evitar valores anteriores.
        campo_usuario.clear()
        campo_contrasena.clear()

        print("[TESTFIRE] Ingresando credenciales...")

        campo_usuario.send_keys(usuario)
        campo_contrasena.send_keys(contrasena)

        # Localizamos el botón Login mediante su atributo name.
        boton_login = self.espera.until(
            EC.element_to_be_clickable(
                (By.NAME, "btnSubmit")
            )
        )

        print("[TESTFIRE] Enviando formulario...")
        boton_login.click()

        try:
            # Esperamos hasta detectar éxito o rechazo.
            self._esperar_resultado_login()

        except TimeoutException:
            # Si la página no entrega un resultado reconocible,
            # igualmente dejamos evidencia para investigar el problema.
            detalle = (
                "Tiempo de espera agotado: no fue posible determinar "
                "el resultado del inicio de sesión."
            )

            print(f"[TESTFIRE] {detalle}")

            ruta_captura = self.navegador.capturar_evidencia(
                id_ejecucion,
                "login_sin_resultado",
            )

            return False, ruta_captura, detalle

        # IMPORTANTE:
        # El error se revisa antes que el éxito. Un mensaje visible de
        # rechazo siempre tiene prioridad sobre cualquier otro elemento.
        mensaje_error = self._obtener_error_login()

        if mensaje_error:
            detalle = (
                "Credenciales incorrectas: el usuario o la "
                "contraseña no fueron encontrados en el sistema."
            )

            print(f"[TESTFIRE] Login rechazado: {detalle}")

            ruta_captura = self.navegador.capturar_evidencia(
                id_ejecucion,
                "login_fallido",
            )

            return False, ruta_captura, detalle

        # Solo informamos éxito si no existe un mensaje de rechazo y
        # además encontramos una señal real de sesión autenticada.
        if self._login_exitoso():
            detalle = "Inicio de sesión realizado correctamente."

            print("[TESTFIRE] Login exitoso.")

            ruta_captura = self.navegador.capturar_evidencia(
                id_ejecucion,
                "login_exitoso",
            )

            return True, ruta_captura, detalle

        # Esta condición es poco probable, pero evita registrar un éxito
        # cuando la página presenta un resultado desconocido.
        detalle = (
            "TestFire respondió, pero el resultado del inicio "
            "de sesión no pudo determinarse."
        )

        print(f"[TESTFIRE] {detalle}")

        ruta_captura = self.navegador.capturar_evidencia(
            id_ejecucion,
            "login_indeterminado",
        )

        return False, ruta_captura, detalle

    def abrir_actividad_cuenta(
        self,
        id_ejecucion: str,
    ) -> tuple[bool, Path, str]:
        """
        Abre la sección de movimientos bancarios de TestFire.
    
        En la interfaz de Altoro Mutual esta opción aparece como
        "View Recent Transactions". Dentro del caso de evaluación
        corresponde a la sección "Account Activity".
    
        El método realiza las siguientes validaciones:
    
        1. Comprueba que exista una sesión iniciada.
        2. Presiona el enlace de movimientos.
        3. Espera que cargue la página transaction.jsp.
        4. Comprueba que aparezca el encabezado Recent Transactions.
        5. Comprueba que exista la tabla de movimientos.
        6. Genera una captura de evidencia.
    
        Args:
            id_ejecucion:
                Identificador único de la ejecución actual. Se utiliza
                para relacionar la captura con los registros de auditoría.
    
        Returns:
            tuple[bool, Path, str]:
                Una tupla con los siguientes datos:
    
                - Resultado de la navegación.
                - Ruta local de la captura.
                - Descripción del resultado.
        """
    
        print(
            "[TESTFIRE] Abriendo la actividad de la cuenta..."
        )
    
        # Antes de navegar, comprobamos que la sesión siga activa.
        # Esto evita intentar acceder a movimientos sin autenticación.
        if not self._login_exitoso():
            detalle = (
                "No se puede abrir la actividad de la cuenta "
                "porque no existe una sesión iniciada."
            )
    
            print(f"[TESTFIRE] {detalle}")
    
            ruta_captura = self.navegador.capturar_evidencia(
                id_ejecucion,
                "actividad_cuenta_sin_sesion",
            )
    
            return False, ruta_captura, detalle
    
        try:
            # MenuHyperLink2 corresponde al enlace visible como
            # "View Recent Transactions".
            enlace_movimientos = self.espera.until(
                EC.element_to_be_clickable(
                    (By.ID, "MenuHyperLink2")
                )
            )
    
            enlace_movimientos.click()
    
            # Esperamos la redirección a la página de movimientos.
            self.espera.until(
                EC.url_contains("/bank/transaction.jsp")
            )
    
            # Verificamos el encabezado de la página. No basta con
            # revisar solamente la URL porque podría cargar incompleta.
            self.espera.until(
                EC.visibility_of_element_located(
                    (
                        By.XPATH,
                        (
                            "//h1[contains("
                            "normalize-space(.), "
                            "'Recent Transactions')]"
                        ),
                    )
                )
            )
    
            # Esperamos la tabla donde TestFire presenta los movimientos.
            # La tabla puede existir aunque no contenga registros.
            self.espera.until(
                EC.visibility_of_element_located(
                    (
                        By.ID,
                        (
                            "_ctl0__ctl0_Content_Main_"
                            "MyTransactions"
                        ),
                    )
                )
            )
    
            detalle = (
                "Se abrió correctamente la sección de movimientos "
                "recientes de TestFire."
            )
    
            print(
                "[TESTFIRE] Actividad de la cuenta cargada "
                "correctamente."
            )
    
            # La captura será posteriormente subida a Google Drive
            # y registrada en Google Sheets desde main.py.
            ruta_captura = self.navegador.capturar_evidencia(
                id_ejecucion,
                "actividad_cuenta",
            )
    
            return True, ruta_captura, detalle
    
        except TimeoutException:
            # Este bloque se ejecuta si el enlace, el encabezado o
            # la tabla no aparecen dentro del tiempo configurado.
            detalle = (
                "Tiempo de espera agotado al abrir la actividad "
                "de la cuenta."
            )
    
            print(f"[TESTFIRE] {detalle}")
    
            ruta_captura = self.navegador.capturar_evidencia(
                id_ejecucion,
                "error_actividad_cuenta",
            )
    
            return False, ruta_captura, detalle  

    def extraer_movimientos(
        self,
        id_ejecucion: str,
    ) -> tuple[bool, list[dict[str, str]], Path, str]:
        """
        Extrae los movimientos visibles en Recent Transactions.

        Cada fila de la tabla se convierte en un diccionario con las
        siguientes propiedades:

        - id_transaccion
        - fecha_hora
        - id_cuenta
        - accion
        - monto

        En esta etapa los valores se conservan como texto. La conversión
        de fechas y montos se realizará posteriormente, cuando preparemos
        el archivo Excel y la conciliación.

        Args:
            id_ejecucion:
                Identificador único de la ejecución actual. Se utiliza
                para nombrar la captura de evidencia.

        Returns:
            tuple[bool, list[dict[str, str]], Path, str]:
                Tupla que contiene:

                - Resultado de la extracción.
                - Lista de movimientos encontrados.
                - Ruta de la captura de evidencia.
                - Descripción del resultado.
        """

        print("[TESTFIRE] Extrayendo movimientos de la tabla...")

        # Verificamos que el navegador se encuentre en la página
        # correcta antes de intentar leer la tabla.
        url_actual = self.driver.current_url.lower()

        if "/bank/transaction.jsp" not in url_actual:
            detalle = (
                "No se pueden extraer movimientos porque el "
                "navegador no está en Recent Transactions."
            )

            print(f"[TESTFIRE] {detalle}")

            ruta_captura = self.navegador.capturar_evidencia(
                id_ejecucion,
                "extraccion_fuera_de_pagina",
            )

            return False, [], ruta_captura, detalle

        try:
            # Esperamos hasta que la tabla esté visible.
            tabla_movimientos = self.espera.until(
                EC.visibility_of_element_located(
                    (
                        By.ID,
                        (
                            "_ctl0__ctl0_Content_Main_"
                            "MyTransactions"
                        ),
                    )
                )
            )

            # Buscamos todas las filas que contienen celdas <td>.
            # Esto incluye la cabecera y las filas de movimientos.
            filas = tabla_movimientos.find_elements(
                By.XPATH,
                ".//tr[td]",
            )

            # Aquí almacenaremos cada movimiento extraído.
            movimientos = []
            self.movimientos_extraidos = movimientos

            # El ciclo for permite procesar cada fila individualmente.
            for fila in filas:
                celdas = fila.find_elements(
                    By.TAG_NAME,
                    "td",
                )

                # Convertimos las celdas en textos limpios,
                # eliminando saltos de línea y espacios repetidos.
                valores = [
                    " ".join(celda.text.split())
                    for celda in celdas
                ]

                # La tabla válida tiene cinco columnas.
                # Si una fila posee menos columnas, se ignora.
                if len(valores) < 5:
                    continue

                # La primera fila contiene los encabezados:
                # Transaction ID, Transaction Time, etc.
                # No debe incluirse como movimiento.
                if valores[0].strip().lower() == "transaction id":
                    continue

                # Ignoramos cualquier fila completamente vacía.
                if not any(valores):
                    continue

                # Convertimos la fila en un diccionario.
                movimiento = {
                    "id_transaccion": valores[0],
                    "fecha_hora": valores[1],
                    "id_cuenta": valores[2],
                    "accion": valores[3],
                    "monto": valores[4],
                }

                movimientos.append(movimiento)

                # Mostramos los datos para comprobar visualmente
                # que cada columna fue extraída correctamente.
                numero_movimiento = len(movimientos)

                print(
                    f"[MOVIMIENTO {numero_movimiento}] "
                    f"ID: {movimiento['id_transaccion']} | "
                    f"Fecha: {movimiento['fecha_hora']} | "
                    f"Cuenta: {movimiento['id_cuenta']} | "
                    f"Acción: {movimiento['accion']} | "
                    f"Monto: {movimiento['monto']}"
                )

            cantidad_movimientos = len(movimientos)

            detalle = (
                "Extracción completada correctamente. "
                f"Movimientos encontrados: {cantidad_movimientos}."
            )

            print(
                "[TESTFIRE] Extracción completada. "
                f"Registros encontrados: {cantidad_movimientos}."
            )

            # Capturamos la tabla que acaba de ser procesada.
            # main.py se encargará posteriormente de subirla a Drive.
            ruta_captura = self.navegador.capturar_evidencia(
                id_ejecucion,
                "movimientos_extraidos",
            )

            return (
                True,
                movimientos,
                ruta_captura,
                detalle,
            )

        except TimeoutException:
            # Se registra un resultado controlado si la tabla no aparece
            # dentro del tiempo máximo configurado.
            detalle = (
                "Tiempo de espera agotado: no se encontró la "
                "tabla de movimientos."
            )

            print(f"[TESTFIRE] {detalle}")

            ruta_captura = self.navegador.capturar_evidencia(
                id_ejecucion,
                "error_extraccion_movimientos",
            )

            return False, [], ruta_captura, detalle
