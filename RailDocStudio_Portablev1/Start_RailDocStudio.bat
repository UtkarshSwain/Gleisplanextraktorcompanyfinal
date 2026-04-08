@echo off
:: ============================================================================
:: RailDoc Studio Launcher
:: Double-click this file to start the application
:: ============================================================================

:: Change to script directory
cd /d "%~dp0"

:: Use ONLY portable Python - ignore any system Python
:: This ensures it works the same way on any computer
set PATH=%~dp0python;%~dp0python\Scripts;%SystemRoot%\System32;%SystemRoot%

:: Set PYTHONPATH to include the application directory
set PYTHONPATH=%~dp0

:: Add PyTorch DLLs to PATH (prevents DLL load errors)
set PATH=%~dp0python\Lib\site-packages\torch\lib;%PATH%

:: Set Tesseract data path
set TESSDATA_PREFIX=%~dp0tesseract

:: Add poppler to PATH for pdf2image
set PATH=%~dp0poppler;%PATH%

:: Run the application
python main.py

:: Keep window open if there was an error
if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to close...
    pause >nul
)
