@echo off
REM ===========================================================================
REM  Arranca el proyecto: API + interfaz, y abre el navegador.
REM
REM  Doble clic sobre este archivo, o en una terminal:  iniciar.cmd
REM
REM  Abre dos ventanas nuevas, una por servidor, para que los registros de cada
REM  uno se lean por separado. Cerrar esas ventanas detiene los servidores.
REM ===========================================================================

setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo   Pronostico energetico SIN - Tecnologico de Antioquia
echo  ============================================================
echo.

REM --- Comprobaciones previas ------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [ERROR] Falta el entorno virtual.
    echo          Ejecuta primero:  instalar.cmd
    goto :fin
)

if not exist ".env" (
    echo  [ERROR] Falta el archivo .env con las credenciales.
    echo          Ejecuta primero:  instalar.cmd
    goto :fin
)

REM Un .env recien copiado de la plantilla no sirve: hay que pegar las
REM credenciales reales. Se detecta por el marcador que trae el ejemplo.
findstr /c:"ep-xxxx" ".env" >nul 2>&1
if not errorlevel 1 (
    echo  [ERROR] El archivo .env todavia tiene los valores de ejemplo.
    echo          Abrelo y pega las credenciales de la base de datos.
    goto :fin
)

if not exist "frontend\node_modules" (
    echo  [ERROR] Faltan las dependencias de la interfaz.
    echo          Ejecuta primero:  instalar.cmd
    goto :fin
)

REM --- Arranque --------------------------------------------------------------
echo  Arrancando la API en el puerto 8000...
start "API - Pronostico SIN" cmd /k ".venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000"

echo  Arrancando la interfaz en el puerto 5173...
start "Interfaz - Pronostico SIN" cmd /k "cd frontend && npm run dev"

REM La interfaz tarda unos segundos en estar lista; abrir el navegador antes
REM mostraria un error de conexion y daria la impresion de que algo fallo.
echo  Esperando a que la interfaz este lista...
timeout /t 8 /nobreak >nul
start "" http://localhost:5173

echo.
echo  ============================================================
echo   Interfaz:       http://localhost:5173
echo   API (docs):     http://localhost:8000/docs
echo.
echo   Cuentas de prueba:
echo     admin@tda.edu.co      Admin123*       (todo)
echo     analista@tda.edu.co   Analista123*    (datos y modelos)
echo     consulta@tda.edu.co   Consulta123*    (vista de usuario)
echo.
echo   Para detenerlo, cierra las dos ventanas que se abrieron.
echo  ============================================================

:fin
echo.
pause
endlocal
