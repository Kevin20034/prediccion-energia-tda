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
echo   Prediccion Energia TdeA
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

REM --- Puertos libres --------------------------------------------------------
REM Si un arranque anterior quedo vivo, el segundo servidor no puede abrir su
REM puerto y la ventana se cierra sola. Avisar aqui evita perseguir el sintoma.
for %%p in (8000 5173) do (
    netstat -ano | findstr /r /c:"LISTENING" | findstr /c:":%%p " >nul 2>&1
    if not errorlevel 1 (
        echo  [ERROR] El puerto %%p ya esta ocupado.
        echo          Cierra las ventanas de un arranque anterior y reintenta.
        goto :fin
    )
)

REM --- Arranque --------------------------------------------------------------
REM Se fija 127.0.0.1 en los dos servidores. Sin indicarlo, Vite se ata solo a
REM la direccion IPv6 (::1); entonces la pagina abre o no segun a que resuelva
REM "localhost" en cada equipo, que es una diferencia invisible y muy molesta de
REM diagnosticar. --strictPort hace que falle a la vista en lugar de saltar en
REM silencio a otro puerto y dejar el navegador apuntando al equivocado.
echo  Arrancando la API en el puerto 8000...
start "API - Pronostico SIN" cmd /k ".venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000"

echo  Arrancando la interfaz en el puerto 5173...
start "Interfaz - Pronostico SIN" cmd /k "cd frontend && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"

REM La interfaz tarda unos segundos en estar lista; abrir el navegador antes
REM mostraria un error de conexion y daria la impresion de que algo fallo.
echo  Esperando a que la interfaz este lista...
timeout /t 8 /nobreak >nul
start "" http://127.0.0.1:5173

echo.
echo  ============================================================
echo   Interfaz:       http://127.0.0.1:5173
echo   API (docs):     http://127.0.0.1:8000/docs
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
REM Ver la nota equivalente en instalar.cmd.
if not "%SIN_PAUSA%"=="1" pause
endlocal
