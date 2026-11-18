@echo off
rem Evaluacion 3 - Subprocesos 2 y 3: dolar de mindicador.cl -> reporte final en Excel.
rem Uso desde Rocketbot: referencia_externa.bat   (toma el discrepancias_*.xlsx mas reciente)
rem                      referencia_externa.bat <ruta discrepancias_X.xlsx>
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "ARG="
if not "%~1"=="" set ARG=--excel "%~1"
%PY% "scripts\referencia_externa_excel.py" %ARG% --salida "%SALIDA%" > "%SALIDA%\referencia_externa_stdout.log" 2>"%SALIDA%\referencia_externa_errores.log"
exit /b %ERRORLEVEL%
