@echo off
rem Evaluacion 3 - Mejora creativa: lo ejecuta el Programador de tareas a las 09:00.
rem Revisa el horario permitido; fuera de horario no corre y deja el intento registrado.
rem Uso manual: ejecutar_robot.bat            (respeta el horario)
rem             ejecutar_robot.bat --forzar   (corre igual y queda registrado que se forzo)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
%PY% "scripts\ejecutar_robot.py" %* >> "%SALIDA%\ejecutar_robot_stdout.log" 2>>"%SALIDA%\ejecutar_robot_errores.log"
exit /b %ERRORLEVEL%
