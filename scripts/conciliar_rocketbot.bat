@echo off
rem Subproceso 2b: concilia consolidado.xlsx contra el maestro SQLite.
rem Uso: conciliar_rocketbot.bat [ruta consolidado.xlsx]  (por defecto, el de la carpeta de salida)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "EXCEL=%~1"
if "%EXCEL%"=="" set "EXCEL=%SALIDA%\consolidado.xlsx"
%PY% "scripts\conciliar_excel_rocketbot.py" --excel "%EXCEL%" --salida "%SALIDA%" > "%SALIDA%\conciliacion_stdout.log" 2>"%SALIDA%\conciliacion_errores.log"
set "CODIGO=%ERRORLEVEL%"
rem Lo que se imprime aqui lo captura Rocketbot (Ejecutar archivo -> variable).
type "%SALIDA%\conciliacion_stdout.log"
if "%CODIGO%"=="0" (echo RESULTADO=OK) else (echo RESULTADO=ERROR)
exit /b %CODIGO%
