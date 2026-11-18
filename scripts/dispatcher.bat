@echo off
rem Evaluacion 3 - Subproceso 4a: encola los correos (no envia nada).
rem Uso desde Rocketbot: dispatcher.bat   (toma el reporte_final_*.xlsx mas reciente)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "ARG="
if not "%~1"=="" set ARG=--excel "%~1"
%PY% "scripts\dispatcher_correos.py" %ARG% > "%SALIDA%\dispatcher_stdout.log" 2>"%SALIDA%\dispatcher_errores.log"
exit /b %ERRORLEVEL%
