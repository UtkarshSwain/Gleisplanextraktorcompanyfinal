@echo off
echo ============================================
echo    TESTING PORTABLE ISOLATION
echo ============================================
echo.

cd /d "%~dp0"

:: Use ONLY portable Python - completely ignore system Python
set PATH=%~dp0python;%~dp0python\Scripts;%SystemRoot%\System32;%SystemRoot%
set PATH=%~dp0python\Lib\site-packages\torch\lib;%PATH%

echo Checking Python location...
where python
echo.

echo Running import test...
python -c "import sys; print('Python executable:', sys.executable); import torch; print('PyTorch:', torch.__version__); import ultralytics; print('Ultralytics: OK'); import PyQt5; print('PyQt5: OK'); import paddleocr; print('PaddleOCR: OK'); print(); print('=== ALL TESTS PASSED - PORTABLE IS WORKING! ===')"

echo.
pause
