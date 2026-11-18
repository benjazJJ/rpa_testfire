@echo off
rem Lanzador para Rocketbot: PATCH contra reqres.in (el modulo nativo no ofrece PATCH).
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
%PY% "scripts\http_reqres_rocketbot.py" --solo PATCH --salida "%SALIDA%" > "%SALIDA%\http_patch_stdout.log" 2>&1
set CODIGO=%ERRORLEVEL%
type "%SALIDA%\http_patch_stdout.log"
exit /b %CODIGO%
