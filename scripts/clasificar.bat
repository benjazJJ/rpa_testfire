@echo off
rem Subproceso 4d: lee las respuestas por IMAP y las clasifica en carpetas.
rem Uso: clasificar.bat            (clasifica y mueve)
rem      clasificar.bat solo-leer  (muestra que haria, sin mover nada)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "OPCION="
if /i "%~1"=="solo-leer" set "OPCION=--solo-leer"
%PY% "scripts\clasificar_respuestas.py" %OPCION% > "%SALIDA%\clasificar_stdout.log" 2>"%SALIDA%\clasificar_errores.log"
set "CODIGO=%ERRORLEVEL%"
rem Lo que se imprime aqui lo captura Rocketbot (Ejecutar archivo -> variable).
type "%SALIDA%\clasificar_stdout.log"
if "%CODIGO%"=="0" (echo RESULTADO=OK) else (echo RESULTADO=ERROR)
exit /b %CODIGO%
