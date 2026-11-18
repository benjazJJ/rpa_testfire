@echo off
rem Evaluacion 3 - Subproceso 4b: envia la cola caso a caso y exporta el tracker al reporte final.
rem Uso desde Rocketbot: performer.bat              (envio real por SMTP)
rem                      performer.bat simulacion   (guarda los correos como .eml, sin enviar)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "CANAL=%~1"
if "%CANAL%"=="" set "CANAL=smtp"
%PY% "scripts\performer_correos.py" --canal %CANAL% --exportar-ultimo > "%SALIDA%\performer_stdout.log" 2>"%SALIDA%\performer_errores.log"
exit /b %ERRORLEVEL%
