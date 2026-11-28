@echo off
rem Subproceso 3 (escritorio): abre el reporte final en Excel, saca captura, guarda y cierra.
rem Uso: abrir_excel.bat [ruta reporte_final_X.xlsx]  (por defecto, el mas reciente)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\abrir_excel.ps1" -Salida "%SALIDA%" -Archivo "%~1" > "%SALIDA%\abrir_excel_stdout.log" 2>"%SALIDA%\abrir_excel_errores.log"
set "CODIGO=%ERRORLEVEL%"
rem Lo que se imprime aqui lo captura Rocketbot (Ejecutar archivo -> variable).
type "%SALIDA%\abrir_excel_stdout.log"
if "%CODIGO%"=="0" (echo RESULTADO=OK) else (echo RESULTADO=ERROR)
exit /b %CODIGO%
