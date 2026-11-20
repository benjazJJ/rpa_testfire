@echo off
rem Regenera el maestro de conciliacion con la extraccion de hoy (Rocketbot_Salida\consolidado.xlsx)
rem y simula 4 diferencias documentadas para que la conciliacion tenga casos reales que mostrar.
rem Ejecutar en el PC ENCOLADOR despues de que el robot haya extraido la tabla.
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
%PY% "scripts\regenerar_master_desde_reporte.py" --simular-diferencias 4
if errorlevel 1 (echo RESULTADO=ERROR) else (echo RESULTADO=OK)
pause
