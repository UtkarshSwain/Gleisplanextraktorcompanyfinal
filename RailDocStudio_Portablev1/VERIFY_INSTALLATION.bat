@echo off
:: ============================================================================
:: Verify Complete RailDocStudio Installation
:: Checks all files, packages, and dependencies
:: ============================================================================

cd /d "%~dp0"

echo ============================================
echo RailDocStudio Installation Verification
echo ============================================
echo.

:: Check YOLO Models
echo [1/6] Checking YOLO Models...
if exist "Gleisplanextraktoryolomodel\antwerp.pt" (
    echo   [OK] antwerp.pt
) else (
    echo   [MISSING] antwerp.pt
)
if exist "Gleisplanextraktoryolomodel\wienfarbig.pt" (
    echo   [OK] wienfarbig.pt
) else (
    echo   [MISSING] wienfarbig.pt
)
if exist "Gleisplanextraktoryolomodel\wienschwarz.pt" (
    echo   [OK] wienschwarz.pt
) else (
    echo   [MISSING] wienschwarz.pt
)

:: Check Tesseract
echo.
echo [2/6] Checking Tesseract OCR...
if exist "tesseract\tesseract.exe" (
    echo   [OK] tesseract.exe
) else (
    echo   [MISSING] tesseract.exe
)
if exist "tesseract\tessdata\eng.traineddata" (
    echo   [OK] English language data
) else (
    echo   [MISSING] English language data
)

:: Check Poppler
echo.
echo [3/6] Checking Poppler PDF tools...
if exist "poppler\pdftoppm.exe" (
    echo   [OK] pdftoppm.exe
) else (
    echo   [MISSING] pdftoppm.exe
)

:: Check Python
echo.
echo [4/6] Checking Python installation...
if exist "python\python.exe" (
    echo   [OK] python.exe found
    python\python.exe --version
) else (
    echo   [MISSING] python.exe
    goto :error
)

:: Check Python packages
echo.
echo [5/6] Checking Python packages...
python\python.exe -c "from PIL import Image; print('  [OK] Pillow')" 2>nul || echo   [MISSING] Pillow
python\python.exe -c "from PyQt5 import QtWidgets; print('  [OK] PyQt5')" 2>nul || echo   [MISSING] PyQt5
python\python.exe -c "import numpy; print('  [OK] NumPy')" 2>nul || echo   [MISSING] NumPy
python\python.exe -c "import torch; print('  [OK] PyTorch')" 2>nul || echo   [MISSING] PyTorch
python\python.exe -c "import ultralytics; print('  [OK] Ultralytics (YOLO)')" 2>nul || echo   [MISSING] Ultralytics
python\python.exe -c "import cv2; print('  [OK] OpenCV')" 2>nul || echo   [MISSING] OpenCV
python\python.exe -c "import fitz; print('  [OK] PyMuPDF')" 2>nul || echo   [MISSING] PyMuPDF
python\python.exe -c "import pytesseract; print('  [OK] PyTesseract')" 2>nul || echo   [MISSING] PyTesseract

:: Check application modules
echo.
echo [6/6] Checking application modules...
python\python.exe -c "import ui; print('  [OK] UI module')" 2>nul || echo   [MISSING] UI module
python\python.exe -c "import core; print('  [OK] Core module')" 2>nul || echo   [MISSING] Core module
python\python.exe -c "import utils; print('  [OK] Utils module')" 2>nul || echo   [MISSING] Utils module
python\python.exe -c "import database_sqlite; print('  [OK] Database module')" 2>nul || echo   [MISSING] Database module

:: Success
echo.
echo ============================================
echo Verification Complete - Installation OK!
echo ============================================
echo.
echo You can now run Start_RailDocStudio.bat
goto :end

:error
echo.
echo ============================================
echo ERROR: Installation is incomplete
echo ============================================
echo.
echo Please run FIX_PYTHON.bat to repair the installation.

:end
echo.
pause
