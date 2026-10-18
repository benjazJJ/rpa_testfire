@echo off
rem Lanzador para Rocketbot: concilia consolidado.xlsx contra el maestro SQLite.
rem Guarda salida y errores en conciliacion_stdout.log para poder depurar.
cd /d "C:\Workspace\rpa_testfire\rpa_testfire"
py "scripts\conciliar_excel_rocketbot.py" --excel "C:\Users\bpalm\Rocketbot_Salida\consolidado.xlsx" --salida "C:\Users\bpalm\Rocketbot_Salida" > "C:\Users\bpalm\Rocketbot_Salida\conciliacion_stdout.log" 2>&1
exit /b %ERRORLEVEL%
