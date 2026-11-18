@echo off
rem Demo para la presentacion: 1000 correos en cola, el 401 con direccion invalida,
rem el 10 con una caida pasajera. Primera pasada se corta en 600 y la segunda retoma.
rem Todo en modo simulacion: no se envia ningun correo real.
cd /d "C:\Workspace\rpa_testfire\rpa_testfire"
set COLA=C:\Users\bpalm\Rocketbot_Salida\cola_demo.db
if exist "%COLA%" del "%COLA%"
py "scripts\dispatcher_correos.py" --demo-volumen 1000 --demo-invalido 401 --lote DEMO_1000 --cola "%COLA%"
py "scripts\performer_correos.py" --cola "%COLA%" --max-envios 600 --demo-fallo-pasajero 10
echo.
echo === Se simulo una caida a los 600. Presiona una tecla para retomar ===
pause > nul
py "scripts\performer_correos.py" --cola "%COLA%" --demo-fallo-pasajero 10 --exportar-excel "C:\Users\bpalm\Rocketbot_Salida\tracker_demo_1000.xlsx" --lote DEMO_1000
pause
