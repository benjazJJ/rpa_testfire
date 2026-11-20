@echo off
rem Deja este PC listo para el robot de la Evaluacion 3.
rem Uso: instalar.bat procesador   (cualquier PC: lee la cola compartida y envia)
rem      instalar.bat encolador    (PC de Gustavo: extrae, concilia y encola)
call "%~dp0entorno.bat"
cd /d "%RAIZ%"
set "ROL=%~1"
if "%ROL%"=="" set "ROL=procesador"
echo ================================================
echo  RPA TestFire - instalando el %ROL% en %COMPUTERNAME%
echo ================================================
echo.
echo [1/5] Python
%PY% --version
if errorlevel 1 (
  echo [X] No hay Python en este PC. Instalalo desde python.org ^(marca 'Add python.exe to PATH'^) y vuelve a ejecutar.
  goto fin
)
echo.
echo [2/5] Librerias
%PY% -m pip install --user --quiet --disable-pip-version-check -r "requirements-eval3.txt"
if errorlevel 1 (
  echo [X] No se pudieron instalar las librerias. Revisa la conexion a internet.
  goto fin
)
echo [OK] openpyxl, requests y psycopg instalados
echo.
echo [3/5] Configuracion
if not exist "config\config.json" (
  echo [X] Falta config\config.json. Copialo desde el PC de Benjamin o Gustavo ^(no esta en GitHub^).
  goto fin
)
echo [OK] config\config.json encontrado
echo.
echo [4/5] Conexiones
%PY% "scripts\probar_cola.py"
if errorlevel 1 goto fin
%PY% "scripts\probar_correo.py"
if errorlevel 1 goto fin
if /i "%ROL%"=="encolador" (
  if not exist "data\entrada\conciliacion_master.db" %PY% "scripts\migrar_master_a_sqlite.py"
)
echo.
echo [5/5] Robot de Rocketbot para este PC
%PY% "scripts\configurar_robot.py" %ROL%
echo.
echo Listo. Importa en Rocketbot Studio el archivo de rocketbot\listo\ que aparece arriba y ejecutalo.
:fin
echo.
pause
