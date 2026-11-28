@echo off
rem Subproceso 2a: escribe la tabla extraida (filas_web.json) en consolidado.xlsx de una sola vez.
rem Reemplaza el For de Rocketbot que escribia celda por celda.
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
%PY% "scripts\guardar_consolidado.py" > "%SALIDA%\guardar_consolidado_stdout.log" 2>"%SALIDA%\guardar_consolidado_errores.log"
set "CODIGO=%ERRORLEVEL%"
rem Lo que se imprime aqui lo captura Rocketbot (Ejecutar archivo -> variable).
type "%SALIDA%\guardar_consolidado_stdout.log"
if "%CODIGO%"=="0" (echo RESULTADO=OK) else (echo RESULTADO=ERROR)
exit /b %CODIGO%
