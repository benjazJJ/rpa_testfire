@echo off
rem Subproceso 4c: prepara el correo al supervisor. Imprime el MENSAJE (Rocketbot lo guarda en una variable)
rem y deja el adjunto en reporte_final_ultimo.xlsx. Rocketbot lo envia con Enviar email SMTP.
rem Uso: resumen_supervisor.bat [ruta reporte_final_X.xlsx]  (por defecto, el mas reciente)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "ARG="
if not "%~1"=="" set ARG=--excel "%~1"
%PY% "scripts\resumen_supervisor.py" %ARG% > "%SALIDA%\resumen_supervisor_stdout.log" 2>"%SALIDA%\resumen_supervisor_errores.log"
set "CODIGO=%ERRORLEVEL%"
rem Lo que se imprime aqui lo captura Rocketbot (Ejecutar archivo -> variable).
if "%CODIGO%"=="4" (
  rem Nada cambio desde el ultimo resumen: no se avisa de nuevo al supervisor.
  echo SIN_NOVEDADES
  echo RESULTADO=OK
  exit /b 0
)
type "%SALIDA%\mensaje_supervisor.txt"
if "%CODIGO%"=="0" (echo RESULTADO=OK) else (echo RESULTADO=ERROR)
exit /b %CODIGO%
