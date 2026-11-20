@echo off
rem Muestra si los robots de este PC estan encendidos y cuando corren la proxima vez.
echo Robots en %COMPUTERNAME%:
echo.
powershell -NoProfile -Command "foreach($n in 'RPA TestFire Encolador','RPA TestFire Procesador'){ $t=Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue; if($t){ $i=$t | Get-ScheduledTaskInfo; '[ON]  {0}: ENCENDIDO - proxima ejecucion {1:dd-MM-yyyy HH:mm}' -f $n,$i.NextRunTime } else { '[OFF] {0}: APAGADO' -f $n } }"
echo.
pause
