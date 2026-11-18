@echo off
rem Evaluacion 3 - Subproceso 4c: prepara para, asunto, mensaje y adjunto del correo al supervisor.
rem Rocketbot lo envia despues con su comando Enviar email SMTP.
rem Uso desde Rocketbot: resumen_supervisor.bat   (usa el reporte_final_*.xlsx mas reciente)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "ARG="
if not "%~1"=="" set ARG=--excel "%~1"
%PY% "scripts\resumen_supervisor.py" %ARG% > "%SALIDA%\resumen_supervisor_stdout.log" 2>"%SALIDA%\resumen_supervisor_errores.log"
exit /b %ERRORLEVEL%
