@echo off
setlocal EnableExtensions

REM Always run relative to the folder containing this script.
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

REM Prefer the Windows Python launcher so a specific Python version can be selected.
set "SYSTEM_PYTHON="
where py >nul 2>&1
if not errorlevel 1 set "SYSTEM_PYTHON=py -3"
if not defined SYSTEM_PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 set "SYSTEM_PYTHON=python"
)
if not defined SYSTEM_PYTHON (
    echo Python 3 was not found. Install Python 3.10 or newer, then run this file again.
    pause
    exit /b 1
)

REM Keep project packages isolated from the system Python installation.
set "VENV_PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo Creating the project virtual environment...
    %SYSTEM_PYTHON% -m venv "%PROJECT_DIR%.venv"
    if errorlevel 1 goto :install_error
)

echo.
echo Installing or updating all project Python packages...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :install_error
"%VENV_PYTHON%" -m pip install -r "%PROJECT_DIR%requirements.txt"
if errorlevel 1 goto :install_error

REM These datasets are required by preprocessing_API and are safe to re-check on each run.
echo Preparing NLTK language data...
"%VENV_PYTHON%" -c "import nltk; [nltk.download(item, quiet=True) for item in ('punkt', 'punkt_tab', 'stopwords', 'wordnet')]"
if errorlevel 1 goto :install_error

echo Building or updating the symptom-only baseline from the tracked dataset...
"%VENV_PYTHON%" "%PROJECT_DIR%model_API\train_baseline.py"
if errorlevel 1 goto :install_error

REM The baseline and RAG index now run from tracked local files; MongoDB is optional.
echo Starting the grounded Baseline API on http://localhost:5000 ...
REM Run the virtual-environment Python by a relative path. This avoids
REM passing the ampersand in "AI & Data science" through a nested cmd.
start "Medical ChatBot - Grounded Baseline API" /D "%PROJECT_DIR%model_API" cmd /k ..\.venv\Scripts\python.exe app.py

echo Starting the Streamlit GUI on http://localhost:8501 ...
start "Medical ChatBot - Streamlit GUI" /D "%PROJECT_DIR%gui" cmd /k ..\.venv\Scripts\python.exe -m streamlit run app.py

echo.
echo The GUI opens at http://localhost:8501
echo Keep the opened terminal windows running while using the ChatBot.
pause
exit /b 0

:install_error
echo.
echo Package setup failed. Check your internet connection, Python installation, and the error above.
pause
exit /b 1
