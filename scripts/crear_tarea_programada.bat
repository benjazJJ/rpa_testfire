@echo off
rem Evaluacion 3 - Crea (o reemplaza) la tarea programada de Windows del robot.
rem Corre de lunes a viernes a las 09:00 con el usuario que ejecuta este .bat.
rem Uso: crear_tarea_programada.bat [HH:MM]   (por defecto 09:00; util para probar a otra hora)
call "%~dp0entorno.bat"
set "HORA=%~1"
if "%HORA%"=="" set "HORA=09:00"
schtasks /create /tn "RPA TestFire Eval3" /tr "\"%RAIZ%\scripts\ejecutar_robot.bat\"" /sc weekly /d MON,TUE,WED,THU,FRI /st %HORA% /f
if errorlevel 1 (
  echo No se pudo crear la tarea. Prueba abriendo la consola como administrador.
  exit /b 1
)
schtasks /query /tn "RPA TestFire Eval3" /fo LIST
echo.
echo Tarea creada. Para verla: Programador de tareas ^> Biblioteca ^> RPA TestFire Eval3
pause
