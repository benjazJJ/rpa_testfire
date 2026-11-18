@echo off
rem Lanzador para Rocketbot: concilia consolidado.xlsx contra el maestro SQLite.
rem Uso: conciliar_rocketbot.bat [ruta consolidado.xlsx]  (por defecto, el de la carpeta de salida)
rem Guarda salida y errores en conciliacion_stdout.log para poder depurar.
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "EXCEL=%~1"
if "%EXCEL%"=="" set "EXCEL=%SALIDA%\consolidado.xlsx"
%PY% "scripts\conciliar_excel_rocketbot.py" --excel "%EXCEL%" --salida "%SALIDA%" > "%SALIDA%\conciliacion_stdout.log" 2>&1
exit /b %ERRORLEVEL%
