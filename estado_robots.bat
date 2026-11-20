@echo off
rem Muestra si los robots de este PC estan encendidos y cuando corren la proxima vez.
for %%T in ("RPA TestFire Encolador" "RPA TestFire Procesador") do (
  schtasks /query /tn %%T /fo LIST 2>nul | findstr /i "Nombre TaskName Pr.xima Next Estado Status" || echo %%~T: APAGADO
  echo.
)
pause
