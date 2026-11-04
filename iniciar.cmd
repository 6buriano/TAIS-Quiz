@echo off
rem Levanta la interfaz de TAIS Quiz en el navegador.
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m quiz servir
) else (
  python -m quiz servir
)

echo.
echo El servidor se detuvo.
pause
