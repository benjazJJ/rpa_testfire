"""
Generación de reportes Excel para el RPA Demo TestFire.

Este módulo recibe los movimientos extraídos mediante Selenium y crea
un archivo Excel estructurado dentro de la carpeta data/salida.

El reporte contiene:

1. Una hoja con el detalle de los movimientos.
2. Una hoja con indicadores y fórmulas de resumen.
3. Una hoja con el resultado detallado de la conciliación.
4. Fechas y montos almacenados con sus tipos correctos.
5. Filtros, formato, colores y filas congeladas.
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo


class GeneradorReporteExcel:
    """
    Genera el reporte Excel de movimientos de Demo TestFire.

    La clase transforma los valores extraídos desde la página web en
    datos utilizables por Excel. Las fechas se convierten a datetime
    y los montos se convierten a números.
    """

    def __init__(self, ruta_salida: Path | str | None = None):
        """
        Inicializa el generador y establece la carpeta de salida.

        Args:
            ruta_salida:
                Carpeta donde se guardarán los archivos Excel.

                Si no se entrega una ruta, se utilizará:

                data/salida
        """

        # __file__ corresponde a src/excel_report.py.
        # parents[1] representa la carpeta principal del proyecto.
        raiz_proyecto = Path(__file__).resolve().parents[1]

        if ruta_salida is None:
            self.ruta_salida = (
                raiz_proyecto
                / "data"
                / "salida"
            )
        else:
            self.ruta_salida = Path(ruta_salida).resolve()

        # Creamos la carpeta automáticamente si aún no existe.
        self.ruta_salida.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Colores utilizados en el reporte.
        self.color_azul_oscuro = "1F4E78"
        self.color_azul_claro = "D9EAF7"
        self.color_verde = "E2F0D9"
        self.color_rojo = "FCE4D6"
        self.color_amarillo = "FFF2CC"
        self.color_blanco = "FFFFFF"
        self.color_gris = "D9E1F2"

        # Borde inferior utilizado para separar encabezados.
        self.borde_encabezado = Border(
            bottom=Side(
                style="thin",
                color="9EADBA",
            )
        )

    def _convertir_fecha(
        self,
        fecha: str | datetime,
    ) -> datetime:
        """
        Convierte la fecha extraída desde TestFire a datetime.

        TestFire entrega normalmente fechas con el formato:

        yyyy-mm-dd HH:MM

        Args:
            fecha:
                Fecha recibida desde Selenium.

        Returns:
            datetime:
                Fecha convertida para que Excel pueda ordenarla,
                filtrarla y utilizarla en cálculos.

        Raises:
            ValueError:
                Cuando la fecha no tiene el formato esperado.
        """

        # Si el valor ya es datetime, no es necesario convertirlo.
        if isinstance(fecha, datetime):
            return fecha

        texto_fecha = str(fecha).strip()

        try:
            return datetime.strptime(
                texto_fecha,
                "%Y-%m-%d %H:%M",
            )

        except ValueError as error:
            raise ValueError(
                "La fecha recibida desde TestFire no tiene "
                f"un formato válido: {texto_fecha}"
            ) from error

    def _convertir_monto(
        self,
        monto: str | int | float | Decimal,
    ) -> float:
        """
        Convierte un monto de TestFire a número decimal.

        Ejemplos admitidos:

        - $1234.00
        - -$1234.00
        - $1,234.00
        - 100
        - -50.25

        Args:
            monto:
                Monto extraído desde la tabla de TestFire.

        Returns:
            float:
                Monto numérico que Excel podrá sumar y comparar.

        Raises:
            ValueError:
                Cuando el monto no puede convertirse.
        """

        # Los valores numéricos se convierten directamente.
        if isinstance(monto, (int, float, Decimal)):
            return float(monto)

        texto_monto = str(monto).strip()

        # Detectamos el formato contable (123.45),
        # que representa un monto negativo.
        es_negativo_contable = (
            texto_monto.startswith("(")
            and texto_monto.endswith(")")
        )

        # Eliminamos símbolos visuales que Excel no necesita.
        texto_limpio = (
            texto_monto
            .replace("$", "")
            .replace(",", "")
            .replace("(", "")
            .replace(")", "")
            .strip()
        )

        try:
            monto_decimal = Decimal(texto_limpio)

        except InvalidOperation as error:
            raise ValueError(
                "El monto recibido desde TestFire no puede "
                f"convertirse a número: {texto_monto}"
            ) from error

        if es_negativo_contable:
            monto_decimal = -abs(monto_decimal)

        return float(monto_decimal)

    def _crear_hoja_movimientos(
        self,
        libro: Workbook,
        movimientos: list[dict[str, str]],
    ):
        """
        Crea y completa la hoja Movimientos.

        Args:
            libro:
                Libro Excel donde se agregará la hoja.

            movimientos:
                Lista de movimientos generada por TestFireBot.

        Returns:
            Worksheet:
                Hoja de movimientos creada y formateada.
        """

        # Reutilizamos la hoja inicial creada por openpyxl.
        hoja = libro.active
        hoja.title = "Movimientos"

        # Ocultamos las líneas predeterminadas para obtener una
        # presentación más limpia.
        hoja.sheet_view.showGridLines = False

        encabezados = [
            "ID Transacción",
            "Fecha/Hora",
            "ID Cuenta",
            "Acción",
            "Monto",
        ]

        hoja.append(encabezados)

        # Recorremos todos los movimientos extraídos.
        for numero_fila, movimiento in enumerate(
            movimientos,
            start=2,
        ):
            try:
                fecha_convertida = self._convertir_fecha(
                    movimiento.get("fecha_hora", "")
                )

                monto_convertido = self._convertir_monto(
                    movimiento.get("monto", "")
                )

            except ValueError as error:
                raise ValueError(
                    "Error al preparar el movimiento "
                    f"{numero_fila - 1}: {error}"
                ) from error

            # Los identificadores se almacenan como texto porque
            # no representan cantidades para realizar cálculos.
            hoja.append(
                [
                    str(
                        movimiento.get(
                            "id_transaccion",
                            "",
                        )
                    ),
                    fecha_convertida,
                    str(
                        movimiento.get(
                            "id_cuenta",
                            "",
                        )
                    ),
                    str(
                        movimiento.get(
                            "accion",
                            "",
                        )
                    ),
                    monto_convertido,
                ]
            )

        # Aplicamos formato al encabezado.
        for celda in hoja[1]:
            celda.fill = PatternFill(
                fill_type="solid",
                fgColor=self.color_azul_oscuro,
            )

            celda.font = Font(
                color=self.color_blanco,
                bold=True,
            )

            celda.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )

            celda.border = self.borde_encabezado

        hoja.row_dimensions[1].height = 24

        # Congelamos el encabezado mientras el usuario se desplaza.
        hoja.freeze_panes = "A2"

        # Aplicamos formato según el tipo de cada columna.
        for fila in range(2, hoja.max_row + 1):
            # Identificadores tratados explícitamente como texto.
            hoja.cell(fila, 1).number_format = "@"
            hoja.cell(fila, 3).number_format = "@"

            # Fecha real ordenable por Excel.
            hoja.cell(fila, 2).number_format = (
                "yyyy-mm-dd hh:mm"
            )

            # Formato monetario con negativos en color rojo.
            hoja.cell(fila, 5).number_format = (
                '"$"#,##0.00;[Red]-"$"#,##0.00'
            )

            # Alineaciones semánticas.
            hoja.cell(fila, 1).alignment = Alignment(
                horizontal="center"
            )
            hoja.cell(fila, 2).alignment = Alignment(
                horizontal="center"
            )
            hoja.cell(fila, 3).alignment = Alignment(
                horizontal="center"
            )
            hoja.cell(fila, 4).alignment = Alignment(
                horizontal="left"
            )
            hoja.cell(fila, 5).alignment = Alignment(
                horizontal="right"
            )

        # Establecemos anchos adecuados para evitar textos cortados.
        anchos_columnas = {
            "A": 18,
            "B": 21,
            "C": 16,
            "D": 18,
            "E": 18,
        }

        for columna, ancho in anchos_columnas.items():
            hoja.column_dimensions[columna].width = ancho

        # Convertimos el rango en una tabla de Excel.
        # La tabla incluye filtros automáticos y filas alternadas.
        if movimientos:
            ultima_fila = hoja.max_row
            referencia_tabla = f"A1:E{ultima_fila}"

            tabla = Table(
                displayName="TablaMovimientos",
                ref=referencia_tabla,
            )

            estilo_tabla = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )

            tabla.tableStyleInfo = estilo_tabla
            hoja.add_table(tabla)

            # Coloreamos automáticamente montos negativos.
            relleno_negativo = PatternFill(
                fill_type="solid",
                fgColor=self.color_rojo,
            )

            hoja.conditional_formatting.add(
                f"E2:E{ultima_fila}",
                CellIsRule(
                    operator="lessThan",
                    formula=["0"],
                    fill=relleno_negativo,
                ),
            )

            # Coloreamos automáticamente montos positivos.
            relleno_positivo = PatternFill(
                fill_type="solid",
                fgColor=self.color_verde,
            )

            hoja.conditional_formatting.add(
                f"E2:E{ultima_fila}",
                CellIsRule(
                    operator="greaterThan",
                    formula=["0"],
                    fill=relleno_positivo,
                ),
            )

        # Configuración de impresión.
        hoja.page_setup.orientation = "landscape"
        hoja.page_setup.fitToWidth = 1
        hoja.page_setup.fitToHeight = 0
        hoja.sheet_properties.pageSetUpPr.fitToPage = True
        hoja.print_title_rows = "1:1"

        return hoja

    def _crear_hoja_conciliacion(
        self,
        libro: Workbook,
        resultados_conciliacion: list[dict[str, Any]],
    ):
        """
        Crea una hoja con el detalle de la conciliación.

        Cada fila indica si el movimiento coincide con el maestro, si
        contiene diferencias o si solamente existe en una de las fuentes.

        Args:
            libro:
                Libro Excel donde se agregará la hoja.

            resultados_conciliacion:
                Lista devuelta por
                ConciliadorMovimientos.conciliar().

        Returns:
            Worksheet:
                Hoja Conciliación creada y formateada.
        """

        hoja = libro.create_sheet("Conciliación")
        hoja.sheet_view.showGridLines = False

        encabezados = [
            "ID Transacción",
            "Fecha/Hora",
            "ID Cuenta",
            "Acción",
            "Monto",
            "Estado conciliación",
            "Detalle",
            "Prioridad",
            "Analista asignado",
        ]

        hoja.append(encabezados)

        for numero_fila, resultado in enumerate(
            resultados_conciliacion,
            start=2,
        ):
            try:
                fecha_convertida = self._convertir_fecha(
                    resultado.get("fecha_hora", "")
                )

                monto_convertido = self._convertir_monto(
                    resultado.get("monto", "")
                )
            except ValueError as error:
                raise ValueError(
                    "Error al preparar el resultado de conciliación "
                    f"{numero_fila - 1}: {error}"
                ) from error

            hoja.append(
                [
                    str(resultado.get("id_transaccion", "")),
                    fecha_convertida,
                    str(resultado.get("id_cuenta", "")),
                    str(resultado.get("accion", "")).title(),
                    monto_convertido,
                    str(
                        resultado.get(
                            "estado_conciliacion",
                            "",
                        )
                    ),
                    str(
                        resultado.get(
                            "detalle_conciliacion",
                            "",
                        )
                    ),
                    # Columnas de src/datos_sinteticos.py; quedan vacías
                    # si la asignación de excepciones no se ejecutó.
                    str(resultado.get("prioridad_revision", "")),
                    str(resultado.get("analista_asignado", "")),
                ]
            )

        # Aplicamos el mismo estilo visual utilizado en Movimientos.
        for celda in hoja[1]:
            celda.fill = PatternFill(
                fill_type="solid",
                fgColor=self.color_azul_oscuro,
            )
            celda.font = Font(
                color=self.color_blanco,
                bold=True,
            )
            celda.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )
            celda.border = self.borde_encabezado

        hoja.row_dimensions[1].height = 24
        hoja.freeze_panes = "A2"

        # Definimos formatos y colores según el resultado de cada fila.
        for fila in range(2, hoja.max_row + 1):
            hoja.cell(fila, 1).number_format = "@"
            hoja.cell(fila, 2).number_format = "yyyy-mm-dd hh:mm"
            hoja.cell(fila, 3).number_format = "@"
            hoja.cell(fila, 5).number_format = (
                '"$"#,##0.00;[Red]-"$"#,##0.00'
            )

            for columna in (1, 2, 3, 6, 8):
                hoja.cell(fila, columna).alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                )

            hoja.cell(fila, 4).alignment = Alignment(
                horizontal="left",
                vertical="center",
            )
            hoja.cell(fila, 5).alignment = Alignment(
                horizontal="right",
                vertical="center",
            )
            hoja.cell(fila, 7).alignment = Alignment(
                horizontal="left",
                vertical="center",
                wrap_text=True,
            )

            estado = hoja.cell(fila, 6).value

            if estado == "Conciliado":
                color_estado = self.color_verde
            elif estado == "Con diferencias":
                color_estado = self.color_amarillo
            else:
                color_estado = self.color_rojo

            hoja.cell(fila, 6).fill = PatternFill(
                fill_type="solid",
                fgColor=color_estado,
            )

        anchos_columnas = {
            "A": 18,
            "B": 21,
            "C": 16,
            "D": 18,
            "E": 18,
            "F": 23,
            "G": 52,
            "H": 12,
            "I": 24,
        }

        for columna, ancho in anchos_columnas.items():
            hoja.column_dimensions[columna].width = ancho

        # La tabla permite filtrar rápidamente por estado de conciliación.
        if resultados_conciliacion:
            tabla = Table(
                displayName="TablaConciliacion",
                ref=f"A1:I{hoja.max_row}",
            )

            tabla.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )

            hoja.add_table(tabla)

        hoja.page_setup.orientation = "landscape"
        hoja.page_setup.fitToWidth = 1
        hoja.page_setup.fitToHeight = 0
        hoja.sheet_properties.pageSetUpPr.fitToPage = True
        hoja.print_title_rows = "1:1"

        return hoja

    def _crear_hoja_resumen(
        self,
        libro: Workbook,
        id_ejecucion: str,
        cantidad_movimientos: int,
        resumen_conciliacion: dict[str, int] | None = None,
    ):
        """
        Crea una hoja con indicadores generales del reporte.

        Los resultados se calculan utilizando fórmulas de Excel. De esta
        forma, si un usuario modifica posteriormente los movimientos,
        el resumen puede actualizarse automáticamente.

        Args:
            libro:
                Libro Excel donde se agregará la hoja.

            id_ejecucion:
                Identificador de la ejecución del RPA.

            cantidad_movimientos:
                Cantidad de movimientos originalmente exportados.

            resumen_conciliacion:
                Indicadores devueltos por la conciliación. Puede ser None
                para mantener compatibilidad con reportes sin conciliación.

        Returns:
            Worksheet:
                Hoja Resumen creada y formateada.
        """

        hoja = libro.create_sheet("Resumen")
        hoja.sheet_view.showGridLines = False

        if resumen_conciliacion is None:
            resumen_conciliacion = {}

        # Dejamos al menos la fila 2 disponible para las fórmulas,
        # incluso si no se encontraron movimientos.
        ultima_fila = max(
            cantidad_movimientos + 1,
            2,
        )

        # Título principal.
        hoja.merge_cells("A1:B1")
        hoja["A1"] = "Resumen de movimientos TestFire"
        hoja["A1"].fill = PatternFill(
            fill_type="solid",
            fgColor=self.color_azul_oscuro,
        )
        hoja["A1"].font = Font(
            color=self.color_blanco,
            bold=True,
            size=14,
        )
        hoja["A1"].alignment = Alignment(
            horizontal="center",
            vertical="center",
        )
        hoja.row_dimensions[1].height = 28

        # Datos de trazabilidad.
        hoja["A3"] = "ID de ejecución"
        hoja["B3"] = id_ejecucion

        hoja["A4"] = "Fecha de generación"
        hoja["B4"] = datetime.now()
        hoja["B4"].number_format = "yyyy-mm-dd hh:mm:ss"

        # Encabezado de indicadores.
        hoja["A6"] = "Indicador"
        hoja["B6"] = "Resultado"

        for celda in hoja[6]:
            celda.fill = PatternFill(
                fill_type="solid",
                fgColor=self.color_azul_oscuro,
            )
            celda.font = Font(
                color=self.color_blanco,
                bold=True,
            )
            celda.alignment = Alignment(
                horizontal="center",
            )

        # Indicadores calculados con fórmulas.
        hoja["A7"] = "Cantidad de movimientos"
        hoja["B7"] = (
            f"=COUNTA('Movimientos'!A2:A{ultima_fila})"
        )

        hoja["A8"] = "Cantidad de depósitos"
        hoja["B8"] = (
            f'=COUNTIF('
            f"'Movimientos'!D2:D{ultima_fila},"
            f'"Deposit")'
        )

        hoja["A9"] = "Cantidad de retiros"
        hoja["B9"] = (
            f'=COUNTIF('
            f"'Movimientos'!D2:D{ultima_fila},"
            f'"Withdrawal")'
        )

        hoja["A10"] = "Monto neto"
        hoja["B10"] = (
            f"=SUM('Movimientos'!E2:E{ultima_fila})"
        )

        hoja["A11"] = "Total clasificado como depósito"
        hoja["B11"] = (
            f'=SUMIF('
            f"'Movimientos'!D2:D{ultima_fila},"
            f'"Deposit",'
            f"'Movimientos'!E2:E{ultima_fila})"
        )

        hoja["A12"] = "Total clasificado como retiro"
        hoja["B12"] = (
            f'=SUMIF('
            f"'Movimientos'!D2:D{ultima_fila},"
            f'"Withdrawal",'
            f"'Movimientos'!E2:E{ultima_fila})"
        )

        # Formato de cantidades.
        for fila in range(7, 10):
            hoja.cell(fila, 2).number_format = "#,##0"

            # Formato monetario.
            # TestFire puede contener montos extremadamente grandes.
            # La notación científica evita que Excel muestre "####".
            for fila in range(10, 13):
                hoja.cell(fila, 2).number_format = (
                '"$"0.00E+00;[Red]-"$"0.00E+00'
            )

        # Estilo de etiquetas.
        for fila in range(3, 13):
            hoja.cell(fila, 1).font = Font(
                bold=True
            )

            hoja.cell(fila, 1).alignment = Alignment(
                vertical="center"
            )

            hoja.cell(fila, 2).alignment = Alignment(
                vertical="center"
            )

        # Coloreamos suavemente la zona de indicadores.
        for fila in range(7, 13):
            hoja.cell(fila, 1).fill = PatternFill(
                fill_type="solid",
                fgColor=self.color_azul_claro,
            )

        # Segunda sección: indicadores de la conciliación.
        hoja["A14"] = "Indicador de conciliación"
        hoja["B14"] = "Resultado"

        for celda in hoja[14]:
            celda.fill = PatternFill(
                fill_type="solid",
                fgColor=self.color_azul_oscuro,
            )
            celda.font = Font(
                color=self.color_blanco,
                bold=True,
            )
            celda.alignment = Alignment(
                horizontal="center",
            )

        indicadores_conciliacion = (
            ("Total en maestro", "total_maestro"),
            ("Conciliados", "conciliados"),
            ("No conciliados", "no_conciliados"),
            ("Con diferencias", "con_diferencias"),
            ("Solo en TestFire", "solo_testfire"),
            ("Solo en maestro", "solo_maestro"),
        )

        for fila, (etiqueta, clave) in enumerate(
            indicadores_conciliacion,
            start=15,
        ):
            hoja.cell(fila, 1, etiqueta)
            hoja.cell(
                fila,
                2,
                resumen_conciliacion.get(clave, 0),
            )
            hoja.cell(fila, 1).font = Font(bold=True)
            hoja.cell(fila, 1).fill = PatternFill(
                fill_type="solid",
                fgColor=self.color_azul_claro,
            )
            hoja.cell(fila, 2).number_format = "#,##0"

        hoja.column_dimensions["A"].width = 34
        hoja.column_dimensions["B"].width = 30

        return hoja

    def generar_reporte(
        self,
        movimientos: list[dict[str, str]],
        id_ejecucion: str,
        resultados_conciliacion: list[dict[str, Any]] | None = None,
        resumen_conciliacion: dict[str, int] | None = None,
        estado_proceso: str = "COMPLETADO",
        motivo: str = "",
        ultima_etapa: str = "Generación del reporte",
    ) -> Path:
        """
        Genera y guarda el reporte Excel completo.

        Args:
            movimientos:
                Lista obtenida desde TestFireBot.extraer_movimientos().

            id_ejecucion:
                Identificador único de la ejecución actual.

            resultados_conciliacion:
                Detalle generado por ConciliadorMovimientos.

            resumen_conciliacion:
                Cantidades generales obtenidas durante la conciliación.

        Returns:
            Path:
                Ruta absoluta del archivo Excel creado.

        Raises:
            TypeError:
                Cuando movimientos no es una lista.

            ValueError:
                Cuando el ID de ejecución está vacío o algún movimiento
                contiene una fecha o monto inválido.
        """

        if not isinstance(movimientos, list):
            raise TypeError(
                "Los movimientos deben entregarse como una lista."
            )

        if not id_ejecucion.strip():
            raise ValueError(
                "El ID de ejecución no puede estar vacío."
            )

        if resultados_conciliacion is None:
            resultados_conciliacion = []

        if resumen_conciliacion is None:
            resumen_conciliacion = {}

        # Limpiamos el ID para evitar caracteres inválidos
        # dentro del nombre del archivo.
        id_seguro = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            id_ejecucion,
        )

        nombre_archivo = (
            f"movimientos_{id_seguro}.xlsx"
        )

        ruta_archivo = (
            self.ruta_salida
            / nombre_archivo
        )

        # Creamos el libro de trabajo.
        libro = Workbook()

        # Propiedades generales del documento.
        libro.properties.title = (
            "Reporte de movimientos Demo TestFire"
        )
        libro.properties.subject = (
            "Movimientos bancarios extraídos por RPA"
        )
        libro.properties.creator = (
            "RPA Demo TestFire"
        )
        libro.properties.description = (
            f"Reporte generado durante la ejecución {id_ejecucion}."
        )

        # Creamos ambas hojas.
        self._crear_hoja_movimientos(
            libro=libro,
            movimientos=movimientos,
        )

        self._crear_hoja_resumen(
            libro=libro,
            id_ejecucion=id_ejecucion,
            cantidad_movimientos=len(movimientos),
            resumen_conciliacion=resumen_conciliacion,
        )

        self._crear_hoja_conciliacion(
            libro=libro,
            resultados_conciliacion=resultados_conciliacion,
        )

        # Dejamos Movimientos como hoja activa al abrir el archivo.
        libro.active = libro.sheetnames.index(
            "Movimientos"
        )

        self._crear_hoja_estado(libro, estado_proceso, motivo, ultima_etapa)
        if estado_proceso == "INCOMPLETO" and not resultados_conciliacion:
            for fila in range(15, 21):
                libro["Resumen"].cell(fila, 2, "No evaluado")

        # Guardamos el archivo en data/salida.
        libro.save(ruta_archivo)

        print(
            f"[EXCEL] Reporte generado: {ruta_archivo.name}"
        )

        return ruta_archivo

    def _crear_hoja_estado(self, libro, estado, motivo, ultima_etapa):
        if "Estado del proceso" in libro.sheetnames:
            del libro["Estado del proceso"]
        hoja = libro.create_sheet("Estado del proceso", 0)
        for fila in (
            ("Campo", "Detalle"),
            ("Estado", estado),
            ("Motivo", motivo),
            ("Fecha y hora", datetime.now()),
            ("Última etapa completada", ultima_etapa),
            ("Observación", "Resultados parciales; requieren revisión."
             if estado == "INCOMPLETO" else
             "Ejecución en curso." if estado == "EN CURSO" else "Proceso terminado."),
        ):
            hoja.append(fila)
        hoja["B4"].number_format = "yyyy-mm-dd hh:mm:ss"
        hoja.column_dimensions["A"].width = 30
        hoja.column_dimensions["B"].width = 85
        for fila in hoja:
            fila[0].font = Font(bold=True)
            fila[1].alignment = Alignment(wrap_text=True, vertical="top")
        hoja["B2"].fill = PatternFill(
            fill_type="solid",
            fgColor=self.color_verde if estado == "COMPLETADO" else self.color_amarillo,
        )
        libro.active = libro.sheetnames.index("Estado del proceso")

    def actualizar_estado(self, ruta, estado, motivo, ultima_etapa):
        """Actualiza únicamente el estado del reporte local existente."""
        libro = load_workbook(ruta)
        try:
            self._crear_hoja_estado(libro, estado, motivo, ultima_etapa)
            libro.save(ruta)
        finally:
            libro.close()
