@echo off
rem Demo para la presentacion: 1000 correos en cola, el 401 con direccion invalida,
rem el 10 con una caida pasajera. La primera pasada se corta en 600 y la segunda retoma.
rem Todo en modo simulacion: no se envia ningun correo real.
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "COLA=%SALIDA%\cola_demo.db"
if exist "%COLA%" del "%COLA%"
%PY% "scripts\dispatcher_correos.py" --demo-volumen 1000 --demo-invalido 401 --lote DEMO_1000 --cola "%COLA%"
%PY% "scripts\performer_correos.py" --cola "%COLA%" --max-envios 600 --demo-fallo-pasajero 10
echo.
echo === Se simulo una caida a los 600. Presiona una tecla para retomar ===
pause > nul
%PY% "scripts\performer_correos.py" --cola "%COLA%" --demo-fallo-pasajero 10 --exportar-excel "%SALIDA%\tracker_demo_1000.xlsx" --lote DEMO_1000
pause
