@echo off
setlocal

set BACKEND_PORT=8000
set FRONTEND_PORT=3000

echo ============================================
echo   EduNexus AI - Starting backend + frontend
echo ============================================
echo.

echo Checking backend on port %BACKEND_PORT%...
netstat -ano | findstr ":%BACKEND_PORT% " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo   Already running - skipping.
) else (
    echo   Starting in a new window...
    start "EduNexus Backend" cmd /k "cd /d %~dp0 && call backend\venv\Scripts\activate.bat && uvicorn backend.main:app --app-dir . --port %BACKEND_PORT%"
)

echo.
echo Starting ingestion worker...
start "EduNexus Ingestion Worker" cmd /k "cd /d %~dp0 && call backend\venv\Scripts\activate.bat && python -m backend.worker"

echo.
echo Checking frontend on port %FRONTEND_PORT%...
netstat -ano | findstr ":%FRONTEND_PORT% " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo   Already running - skipping.
) else (
    echo   Starting in a new window...
    start "EduNexus Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
)

echo.
echo Waiting for servers to warm up...
echo (first cold start can take 20-30s while the embedding model loads -
echo  if the page looks broken on first load, just refresh in a few seconds)
ping -n 7 127.0.0.1 >nul

echo Opening http://localhost:%FRONTEND_PORT% ...
start http://localhost:%FRONTEND_PORT%

echo.
echo Done. This window will close shortly.
echo (The backend and frontend keep running in their own windows -
echo  closing those stops the servers; closing this one does not.)
ping -n 6 127.0.0.1 >nul

endlocal
