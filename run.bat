@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ENV_NAME=soppo"

where conda >nul 2>nul
if errorlevel 1 (
    echo ERROR: conda was not found on PATH. Use Anaconda Prompt or run setup.bat from a shell where conda works.
    pause
    exit /b 1
)

conda env list | findstr /i /r "^%ENV_NAME% " >nul 2>nul
if errorlevel 1 (
    echo Environment "%ENV_NAME%" not found. Run setup.bat first.
    pause
    exit /b 1
)

if not exist "%~dp0.env" (
    echo WARNING: No .env file found. Copy .env.example to .env and set DISCORD_BOT_TOKEN.
    echo.
)

echo Starting SOPPO_Python...
echo.

REM conda run avoids needing "conda activate" in plain cmd.exe
call conda run --no-capture-output -n "%ENV_NAME%" python "%~dp0main.py"
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo Bot exited with code %EXITCODE%.
    pause
)

endlocal & exit /b %EXITCODE%
