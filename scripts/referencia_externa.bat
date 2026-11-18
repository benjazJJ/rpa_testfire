@echo off
rem Subprocesos 2c y 3: dolar de mindicador.cl -> reporte_final_X.xlsx (columna monto_clp + hoja Referencia externa).
rem Uso: referencia_externa.bat [ruta discrepancias_X.xlsx]  (por defecto, el mas reciente)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "ARG="
if not "%~1"=="" set ARG=--excel "%~1"
%PY% "scripts\referencia_externa_excel.py" %ARG% --salida "%SALIDA%" > "%SALIDA%\referencia_externa_stdout.log" 2>"%SALIDA%\referencia_externa_errores.log"
set "CODIGO=%ERRORLEVEL%"
rem Lo que se imprime aqui lo captura Rocketbot (Ejecutar archivo -> variable).
type "%SALIDA%\referencia_externa_stdout.log"
if "%CODIGO%"=="0" (echo RESULTADO=OK) else (echo RESULTADO=ERROR)
exit /b %CODIGO%
