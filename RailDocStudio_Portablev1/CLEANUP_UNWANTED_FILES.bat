@echo off
:: ============================================================================
:: Cleanup Unwanted Files - Remove temporary and backup files
:: Run this ONLY after confirming the application works correctly
:: ============================================================================

cd /d "%~dp0"

echo ============================================
echo Cleaning Up Unwanted Files
echo ============================================
echo.
echo This will delete:
echo   1. python_broken folder (old broken Python backup - ~500 MB)
echo   2. __pycache__ directories (Python bytecode cache - will regenerate)
echo   3. FIX_PYTHON.bat (repair script - no longer needed)
echo   4. TEST_ISOLATION.bat (testing script)
echo.
echo WARNING: Make sure the application works correctly before running this!
echo.
pause

:: Delete python_broken folder (the old broken installation)
if exist python_broken (
    echo.
    echo Deleting python_broken folder...
    rmdir /s /q python_broken
    if exist python_broken (
        echo ERROR: Could not delete python_broken folder
    ) else (
        echo SUCCESS: python_broken folder deleted
    )
)

:: Delete application __pycache__ directories (not the ones in site-packages)
echo.
echo Deleting application __pycache__ directories...
if exist __pycache__ rmdir /s /q __pycache__
if exist core\__pycache__ rmdir /s /q core\__pycache__
if exist pdfcomparison\__pycache__ rmdir /s /q pdfcomparison\__pycache__
if exist ui\__pycache__ rmdir /s /q ui\__pycache__
if exist uservalidation\__pycache__ rmdir /s /q uservalidation\__pycache__
if exist utils\__pycache__ rmdir /s /q utils\__pycache__
echo SUCCESS: Application cache directories deleted

:: Delete fix script
echo.
echo Deleting FIX_PYTHON.bat...
if exist FIX_PYTHON.bat (
    del FIX_PYTHON.bat
    echo SUCCESS: FIX_PYTHON.bat deleted
)

:: Delete test script
echo.
echo Deleting TEST_ISOLATION.bat...
if exist TEST_ISOLATION.bat (
    del TEST_ISOLATION.bat
    echo SUCCESS: TEST_ISOLATION.bat deleted
)

:: Delete requirements.txt (optional - keep if you want to reinstall packages later)
echo.
set /p DELETE_REQUIREMENTS="Delete requirements.txt? (y/N): "
if /i "%DELETE_REQUIREMENTS%"=="y" (
    if exist requirements.txt (
        del requirements.txt
        echo SUCCESS: requirements.txt deleted
    )
) else (
    echo SKIPPED: requirements.txt kept (can be used for reinstalling packages)
)

echo.
echo ============================================
echo Cleanup Complete!
echo ============================================
echo.
echo You can now delete this cleanup script (CLEANUP_UNWANTED_FILES.bat) manually.
echo.
pause
