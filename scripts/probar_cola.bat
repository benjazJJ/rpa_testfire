@echo off
rem Prueba la conexion de este PC a la cola compartida (Neon).
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
%PY% "scripts\probar_cola.py"
pause
