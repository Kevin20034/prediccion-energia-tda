@echo off
REM ===========================================================================
REM  Instalacion en una maquina nueva.  Se ejecuta UNA sola vez.
REM
REM  Doble clic sobre este archivo, o en una terminal:  instalar.cmd
REM
REM  Es un .cmd y no un .ps1 a proposito: PowerShell bloquea por defecto la
REM  ejecucion de scripts sin firmar, y pedirle a alguien que cambie la
REM  politica de ejecucion de su equipo para instalar un trabajo de grado es
REM  demasiado pedir.
REM ===========================================================================

setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo   Pronostico energetico SIN - Tecnologico de Antioquia
echo   Instalacion
echo  ============================================================
echo.

REM --- 1. Python -------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] No se encontro Python.
    echo          Instalalo desde https://www.python.org/downloads/
    echo          IMPORTANTE: marca "Add Python to PATH" durante la instalacion.
    goto :fin
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [1/5] Python %PYVER% encontrado.

REM --- 2. Entorno virtual ----------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo  [2/5] El entorno virtual ya existe, se reutiliza.
) else (
    echo  [2/5] Creando el entorno virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] No se pudo crear el entorno virtual.
        goto :fin
    )
)

REM --- 3. Dependencias de Python --------------------------------------------
echo  [3/5] Instalando dependencias de Python. Esto tarda varios minutos:
echo        se descarga PyTorch, que ocupa unos 200 MB.
echo.
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Fallo la instalacion de dependencias.
    goto :fin
)

REM --- 4. Dependencias del frontend -----------------------------------------
where npm >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] No se encontro Node.js, que hace falta para la interfaz.
    echo          Instalalo desde https://nodejs.org y vuelve a ejecutar esto.
    goto :fin
)

echo.
echo  [4/5] Instalando dependencias de la interfaz...
pushd frontend
call npm install --no-fund --no-audit
popd
if errorlevel 1 (
    echo  [ERROR] Fallo la instalacion de la interfaz.
    goto :fin
)

REM --- 5. Archivo de configuracion ------------------------------------------
if exist ".env" (
    echo  [5/5] El archivo .env ya existe, no se toca.
    echo.
    echo  ============================================================
    echo   Listo. Arranca el proyecto con:  iniciar.cmd
    echo  ============================================================
) else (
    copy /y ".env.example" ".env" >nul
    echo  [5/5] Se creo el archivo .env a partir de la plantilla.
    echo.
    echo  ============================================================
    echo   FALTA UN PASO
    echo  ============================================================
    echo.
    echo   Abre el archivo .env y pega las credenciales de la base de
    echo   datos que te pasaron por privado. Sin ellas el proyecto no
    echo   puede arrancar.
    echo.
    echo   Las credenciales NO viajan en el repositorio a proposito:
    echo   una clave subida a git queda en el historial para siempre.
    echo.
    echo   Cuando lo tengas, arranca con:  iniciar.cmd
    echo  ============================================================
)

:fin
echo.
REM La pausa existe para quien llega por doble clic: sin ella la ventana se
REM cierra y no se llega a leer si algo fallo. Con SIN_PAUSA=1 se omite, para
REM poder encadenar este script desde otro o desde una comprobacion automatica.
if not "%SIN_PAUSA%"=="1" pause
endlocal
