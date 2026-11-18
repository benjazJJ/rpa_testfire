@echo off
rem Variables comunes de todos los lanzadores: funcionan en cualquier PC sin editar rutas.
rem   RAIZ   = carpeta del repo (la de arriba de scripts), donde sea que se haya clonado.
rem   SALIDA = %USERPROFILE%\Rocketbot_Salida, o la carpeta que indique la variable RPA_SALIDA.
rem   PY     = el lanzador py si esta instalado; si no, python.
for %%I in ("%~dp0..") do set "RAIZ=%%~fI"
if defined RPA_SALIDA (set "SALIDA=%RPA_SALIDA%") else (set "SALIDA=%USERPROFILE%\Rocketbot_Salida")
if not exist "%SALIDA%" mkdir "%SALIDA%"
rem UTF-8 en Python y en la consola: las tildes llegan bien a los logs y a Rocketbot.
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PY=python"
where py >nul 2>nul && set "PY=py"
exit /b 0
