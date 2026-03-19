@echo off
:: ============================================================================
:: RailDoc Studio - Update Portable Distribution
:: Use this to sync code changes without rebuilding everything
:: ============================================================================

echo ============================================================
echo    Updating Portable Distribution (Code Only)
echo ============================================================
echo.

set "SRC=c:\Users\z0054cxa\Documents\Masterarbeit\Gleisplanextraktorv3"
set "DST=c:\Users\z0054cxa\Documents\Masterarbeit\Gleisplanextraktorv3\RailDocStudio_Portable"

if not exist "%DST%" (
    echo ERROR: Portable folder not found!
    echo Run build_portable.bat first.
    pause
    exit /b 1
)

echo [1/6] Updating root Python files...
copy /Y "%SRC%\*.py" "%DST%\" >nul
echo       Done.

echo [2/6] Updating core/ folder...
xcopy /E /Y /Q "%SRC%\core\*.py" "%DST%\core\" >nul
echo       Done.

echo [3/6] Updating ui/ folder...
xcopy /E /Y /Q "%SRC%\ui\*.py" "%DST%\ui\" >nul
echo       Done.

echo [4/6] Updating utils/ folder...
xcopy /E /Y /Q "%SRC%\utils\*.py" "%DST%\utils\" >nul
echo       Done.

echo [5/6] Updating pdfcomparison/ folder...
xcopy /E /Y /Q "%SRC%\pdfcomparison\*.py" "%DST%\pdfcomparison\" >nul
echo       Done.

echo [6/6] Updating uservalidation/ folder...
xcopy /E /Y /Q "%SRC%\uservalidation\*.py" "%DST%\uservalidation\" >nul
echo       Done.

echo.
echo ============================================================
echo    UPDATE COMPLETE!
echo ============================================================
echo.
echo Only Python code was updated.
echo Python environment, models, and tools were NOT changed.
echo.
pause
