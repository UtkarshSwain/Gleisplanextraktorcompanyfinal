@echo off
:: ============================================================================
:: RailDoc Studio - Create ZIP for Distribution
:: Run this after build_portable.bat to create a ZIP file
:: ============================================================================

echo ============================================================
echo    Creating ZIP file for distribution...
echo ============================================================
echo.

set "SOURCE_DIR=%~dp0"
set "PORTABLE_DIR=%SOURCE_DIR%RailDocStudio_Portable"
set "ZIP_FILE=%SOURCE_DIR%RailDocStudio_v2.0.zip"

:: Check if portable folder exists
if not exist "%PORTABLE_DIR%" (
    echo ERROR: RailDocStudio_Portable folder not found!
    echo Please run build_portable.bat first.
    pause
    exit /b 1
)

:: Delete old ZIP if exists
if exist "%ZIP_FILE%" (
    echo Deleting old ZIP file...
    del "%ZIP_FILE%"
)

echo Creating ZIP file (this may take a few minutes)...
powershell -Command "Compress-Archive -Path '%PORTABLE_DIR%' -DestinationPath '%ZIP_FILE%' -CompressionLevel Optimal"

if exist "%ZIP_FILE%" (
    echo.
    echo ============================================================
    echo    ZIP CREATED SUCCESSFULLY!
    echo ============================================================
    echo.
    echo File: %ZIP_FILE%
    echo.
    for %%A in ("%ZIP_FILE%") do echo Size: %%~zA bytes
    echo.
    echo You can now share this ZIP file with your boss!
) else (
    echo.
    echo ERROR: Failed to create ZIP file.
)

pause
