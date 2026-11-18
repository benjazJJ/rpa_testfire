@echo off
rem Evaluacion 3 - Subproceso 4b: procesa la cola caso a caso y exporta el tracker.
rem Uso desde Rocketbot: performer.bat <ruta reporte_final_X.xlsx>
rem Canal: simulacion (deja los correos como .eml). Cambiar cuando se defina Outlook.
cd /d "C:\Workspace\rpa_testfire\rpa_testfire"
py "scripts\performer_correos.py" --canal simulacion --exportar-excel "%~1" > "C:\Users\bpalm\Rocketbot_Salida\performer_stdout.log" 2>&1
exit /b %ERRORLEVEL%
