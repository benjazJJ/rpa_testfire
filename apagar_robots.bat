@echo off
rem BOTON APAGAR: quita las tareas programadas de los robots de ESTE PC. No borra la cola ni los datos.
call "%~dp0scripts\entorno.bat"
set "HABIA="
schtasks /query /tn "RPA TestFire Encolador" >nul 2>nul && (schtasks /delete /tn "RPA TestFire Encolador" /f >nul & set "HABIA=1" & echo [OFF] Encolador apagado)
schtasks /query /tn "RPA TestFire Procesador" >nul 2>nul && (schtasks /delete /tn "RPA TestFire Procesador" /f >nul & set "HABIA=1" & echo [OFF] Procesador apagado)
schtasks /query /tn "RPA TestFire Eval3" >nul 2>nul && (schtasks /delete /tn "RPA TestFire Eval3" /f >nul & set "HABIA=1" & echo [OFF] Tarea antigua RPA TestFire Eval3 eliminada)
if not defined HABIA (echo Los robots ya estaban apagados en este PC.) else (%PY% "%RAIZ%\scripts\registrar_interruptor.py" APAGADO todos)
echo.
echo Los robots ya no corren solos. Puedes seguir ejecutandolos a mano en Rocketbot.
pause
