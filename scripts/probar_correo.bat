@echo off
rem Prueba la cuenta de correo de config\config.json (SMTP e IMAP) antes de correr el robot.
rem Uso: probar_correo.bat                       (solo inicia sesion)
rem      probar_correo.bat be.palmap@duocuc.cl   (ademas envia un correo de prueba)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
if "%~1"=="" (%PY% "scripts\probar_correo.py") else (%PY% "scripts\probar_correo.py" --enviar "%~1")
pause
