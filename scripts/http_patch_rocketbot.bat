@echo off
rem Lanzador para Rocketbot: PATCH contra reqres.in (el modulo nativo no ofrece PATCH).
cd /d "C:\Workspace\rpa_testfire\rpa_testfire"
py "scripts\http_reqres_rocketbot.py" --solo PATCH --salida "C:\Users\bpalm\Rocketbot_Salida" > "C:\Users\bpalm\Rocketbot_Salida\http_patch_stdout.log" 2>&1
set CODIGO=%ERRORLEVEL%
type "C:\Users\bpalm\Rocketbot_Salida\http_patch_stdout.log"
exit /b %CODIGO%
