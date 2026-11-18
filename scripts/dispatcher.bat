@echo off
rem Subproceso 4a: encola los correos (no envia nada).
rem Uso: dispatcher.bat [ruta reporte_final_X.xlsx]  (por defecto, el mas reciente)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "ARG="
if not "%~1"=="" set ARG=--excel "%~1"
%PY% "scripts\dispatcher_correos.py" %ARG% > "%SALIDA%\dispatcher_stdout.log" 2>"%SALIDA%\dispatcher_errores.log"
set "CODIGO=%ERRORLEVEL%"
rem Lo que se imprime aqui lo captura Rocketbot (Ejecutar archivo -> variable).
type "%SALIDA%\dispatcher_stdout.log"
if "%CODIGO%"=="0" (echo RESULTADO=OK) else (echo RESULTADO=ERROR)
exit /b %CODIGO%
