@echo off
rem Evaluacion 3 - Subprocesos 2 y 3: dolar de mindicador.cl -> reporte final en Excel.
rem Uso desde Rocketbot: referencia_externa.bat <ruta discrepancias_X.xlsx>
rem Deja en referencia_externa_stdout.log la linea JSON con la ruta del reporte final.
cd /d "C:\Workspace\rpa_testfire\rpa_testfire"
py "scripts\referencia_externa_excel.py" --excel "%~1" --salida "C:\Users\bpalm\Rocketbot_Salida" > "C:\Users\bpalm\Rocketbot_Salida\referencia_externa_stdout.log" 2>&1
exit /b %ERRORLEVEL%
