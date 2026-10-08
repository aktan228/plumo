@echo off
rem Plumo dev commands for Windows. Works without activating .venv and
rem without changing the PowerShell execution policy.
rem
rem   dev setup    create .venv, install dependencies, copy .env
rem   dev db       start local PostgreSQL (downloads once into .tools)
rem   dev db-stop  stop local PostgreSQL
rem   dev seed     apply migrations and load the demo business
rem   dev run      start the API on http://127.0.0.1:8000/docs
rem   dev demo     chat with the agent in the terminal
rem   dev test     run all tests
rem   dev eval     live 10-turn dialog with the real model
rem   dev up       db + seed + run

setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
set "PYTHONIOENCODING=utf-8"

if "%~1"=="" goto help
if /i "%~1"=="setup" goto setup
if not exist "%PY%" (
    echo .venv not found. Run: dev setup
    exit /b 1
)
if /i "%~1"=="db" goto db
if /i "%~1"=="db-stop" goto dbstop
if /i "%~1"=="seed" goto seed
if /i "%~1"=="run" goto run
if /i "%~1"=="demo" goto demo
if /i "%~1"=="test" goto test
if /i "%~1"=="eval" goto eval
if /i "%~1"=="up" goto up
goto help

:setup
if not exist "%PY%" (
    rem "py" is the official launcher; "python" may be the Microsoft Store stub.
    py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist "%PY%" (
    echo Python 3.12+ not found. Install it from https://www.python.org/downloads/ and tick "Add to PATH".
    exit /b 1
)
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -e ".[dev]"
if not exist ".env" copy ".env.example" ".env" >nul && echo Created .env from .env.example
echo.
echo Ready. Next: dev up
exit /b 0

:db
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\local-db.ps1" start
exit /b %errorlevel%

:dbstop
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\local-db.ps1" stop
exit /b %errorlevel%

:seed
"%PY%" -m app.seed
exit /b %errorlevel%

:run
echo Swagger: http://127.0.0.1:8000/docs
"%PY%" -m uvicorn app.main:app --reload
exit /b %errorlevel%

:demo
"%PY%" -m app.demo --interactive
exit /b %errorlevel%

:test
"%PY%" -m pytest %2 %3 %4
exit /b %errorlevel%

:eval
"%PY%" -m app.eval_live %2 %3 %4 %5 %6 %7
exit /b %errorlevel%

:up
call "%~f0" db || exit /b 1
call "%~f0" seed || exit /b 1
call "%~f0" run
exit /b %errorlevel%

:help
echo Usage: dev ^<setup^|db^|db-stop^|seed^|run^|demo^|test^|eval^|up^>
echo   first time:  dev setup
echo   every day:   dev up      (then open http://127.0.0.1:8000/docs)
exit /b 1
