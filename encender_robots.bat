@echo off
rem BOTON ENCENDER: activa el modo horario de los robots en ESTE PC.
rem   Encolador : lunes a viernes a las 09:00 (un lote nuevo por dia).
rem   Procesador: lunes a viernes cada 30 min entre 08:00 y 18:00 (envia lo pendiente y clasifica respuestas).
rem Para detenerlos: apagar_robots.bat
call "%~dp0scripts\entorno.bat"
echo ================================================
echo  RPA TestFire - ENCENDER modo horario en %COMPUTERNAME%
echo ================================================
echo  E = Encolador  (PC de Gustavo)
echo  P = Procesador (PC que lee la cola)
choice /c EP /m "Que robot corre en este PC"
if errorlevel 2 (set "ROL=procesador") else (set "ROL=encolador")
%PY% "%RAIZ%\scripts\ejecutar_robot.py" --rol %ROL% --revisar-instalacion
if errorlevel 1 (
  echo [X] Corrige la seccion "ejecucion" de config\config.json y vuelve a encender.
  goto fin
)
if "%ROL%"=="encolador" (
  schtasks /create /tn "RPA TestFire Encolador" /tr "\"%RAIZ%\scripts\ejecutar_robot.bat\" --rol encolador" /sc weekly /d MON,TUE,WED,THU,FRI /st 09:00 /f
) else (
  schtasks /create /tn "RPA TestFire Procesador" /tr "\"%RAIZ%\scripts\ejecutar_robot.bat\" --rol procesador" /sc weekly /d MON,TUE,WED,THU,FRI /st 08:00 /ri 30 /du 10:00 /f
)
if errorlevel 1 (
  echo [X] No se pudo crear la tarea. Prueba con clic derecho ^> Ejecutar como administrador.
  goto fin
)
%PY% "%RAIZ%\scripts\registrar_interruptor.py" ENCENDIDO %ROL%
echo.
echo [ON] Robot %ROL% ENCENDIDO en modo horario. Para detenerlo: apagar_robots.bat
:fin
echo.
pause
