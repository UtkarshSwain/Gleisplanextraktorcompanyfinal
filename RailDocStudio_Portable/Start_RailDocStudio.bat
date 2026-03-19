@echo off
:: ============================================================================
:: RailDoc Studio Launcher
:: Double-click this file to start the application
:: ============================================================================

:: Change to script directory
cd /d "%~dp0"

:: Set Python path (for portable distribution)
set PATH=%~dp0python\Scripts;%~dp0python;%PATH%

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
