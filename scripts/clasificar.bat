@echo off
rem Evaluacion 3 - Subproceso 4d: lee las respuestas por IMAP y las clasifica en carpetas.
rem Uso desde Rocketbot: clasificar.bat            (clasifica y mueve)
rem                      clasificar.bat solo-leer  (muestra que haria, sin mover nada)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "OPCION="
if /i "%~1"=="solo-leer" set "OPCION=--solo-leer"
%PY% "scripts\clasificar_respuestas.py" %OPCION% > "%SALIDA%\clasificar_stdout.log" 2>"%SALIDA%\clasificar_errores.log"
exit /b %ERRORLEVEL%
