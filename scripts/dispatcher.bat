@echo off
rem Evaluacion 3 - Subproceso 4a: encola los correos (no envia nada).
rem Uso desde Rocketbot: dispatcher.bat <ruta reporte_final_X.xlsx>
cd /d "C:\Workspace\rpa_testfire\rpa_testfire"
py "scripts\dispatcher_correos.py" --excel "%~1" > "C:\Users\bpalm\Rocketbot_Salida\dispatcher_stdout.log" 2>&1
exit /b %ERRORLEVEL%
