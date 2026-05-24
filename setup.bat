@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ENV_NAME=soppo"

where conda >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERROR: conda was not found on PATH.
    echo Install Anaconda/Miniconda, or run this script from an "Anaconda Prompt",
    echo or add your Anaconda "Scripts" and "condabin" folders to PATH.
    echo.
    pause
    exit /b 1
)

echo.
echo === SOPPO_Python setup (Conda environment: %ENV_NAME%) ===
echo.

REM If the env already exists, skip create (avoids "already exists" failure)
conda env list | findstr /i /r "^%ENV_NAME% " >nul 2>nul
if errorlevel 1 (
    echo Creating conda environment "%ENV_NAME%" with Python 3.11...
    call conda create -n "%ENV_NAME%" python=3.11 -y
    if errorlevel 1 (
        echo conda create failed.
        pause
        exit /b 1
    )
) else (
    echo Conda environment "%ENV_NAME%" already exists — skipping create.
)

echo.
echo Upgrading pip and installing packages from requirements.txt...
call conda run -n "%ENV_NAME%" python -m pip install --upgrade pip
if errorlevel 1 (
    echo pip upgrade failed.
    pause
    exit /b 1
)

call conda run -n "%ENV_NAME%" pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo pip install failed.
    pause
    exit /b 1
)

echo.
echo Setup finished. Run run.bat to start the bot.
echo.
pause
endlocal
