@echo off
:: ============================================================================
:: RailDoc Studio - Portable Distribution Builder
:: Run this script to create a portable folder for distribution
:: ============================================================================

setlocal enabledelayedexpansion

echo ============================================================
echo    RailDoc Studio - Building Portable Distribution
echo ============================================================
echo.

:: Set source directory (where this script is located)
set "SOURCE_DIR=%~dp0"
set "DEST_DIR=%SOURCE_DIR%RailDocStudio_Portable"

:: Check if destination already exists
if exist "%DEST_DIR%" (
    echo WARNING: %DEST_DIR% already exists!
    echo Do you want to delete it and create fresh? (Y/N)
    set /p CONFIRM=
    if /i "!CONFIRM!"=="Y" (
        echo Deleting old folder...
        rmdir /s /q "%DEST_DIR%"
    ) else (
        echo Aborted.
        pause
        exit /b 1
    )
)

echo.
echo [1/8] Creating destination folder...
mkdir "%DEST_DIR%"

echo [2/8] Copying Python environment (~1-2 GB, please wait)...
xcopy /E /I /Q "%SOURCE_DIR%venv\Lib" "%DEST_DIR%\python\Lib" >nul
xcopy /E /I /Q "%SOURCE_DIR%venv\Scripts" "%DEST_DIR%\python\Scripts" >nul
copy /Y "%SOURCE_DIR%venv\pyvenv.cfg" "%DEST_DIR%\python\" >nul
echo       Python environment copied.

echo [3/8] Copying Tesseract OCR...
xcopy /E /I /Q "%SOURCE_DIR%venv\tesseract" "%DEST_DIR%\tesseract" >nul
echo       Tesseract copied.

echo [4/8] Copying Poppler PDF tools...
if exist "%SOURCE_DIR%venv\poppler-25.12.0\Library\bin" (
    xcopy /E /I /Q "%SOURCE_DIR%venv\poppler-25.12.0\Library\bin" "%DEST_DIR%\poppler" >nul
) else if exist "%SOURCE_DIR%venv\poppler-24.08.0\Library\bin" (
    xcopy /E /I /Q "%SOURCE_DIR%venv\poppler-24.08.0\Library\bin" "%DEST_DIR%\poppler" >nul
) else (
    echo       WARNING: Poppler not found in expected location!
)
echo       Poppler copied.

echo [5/8] Copying YOLO models (~226 MB)...
xcopy /E /I /Q "%SOURCE_DIR%Gleisplanextraktoryolomodel" "%DEST_DIR%\Gleisplanextraktoryolomodel" >nul
echo       YOLO models copied.

echo [6/8] Copying application source code...
:: Copy Python packages
xcopy /E /I /Q "%SOURCE_DIR%core" "%DEST_DIR%\core" >nul
xcopy /E /I /Q "%SOURCE_DIR%ui" "%DEST_DIR%\ui" >nul
xcopy /E /I /Q "%SOURCE_DIR%utils" "%DEST_DIR%\utils" >nul
xcopy /E /I /Q "%SOURCE_DIR%uservalidation" "%DEST_DIR%\uservalidation" >nul
xcopy /E /I /Q "%SOURCE_DIR%pdfcomparison" "%DEST_DIR%\pdfcomparison" >nul

:: Copy config folders
xcopy /E /I /Q "%SOURCE_DIR%profiles" "%DEST_DIR%\profiles" >nul
xcopy /E /I /Q "%SOURCE_DIR%config" "%DEST_DIR%\config" >nul

:: Copy root Python files
copy /Y "%SOURCE_DIR%*.py" "%DEST_DIR%\" >nul

:: Copy data folder if exists (contains database)
if exist "%SOURCE_DIR%data" (
    xcopy /E /I /Q "%SOURCE_DIR%data" "%DEST_DIR%\data" >nul
)
echo       Source code copied.

echo [7/8] Copying launcher script...
copy /Y "%SOURCE_DIR%Start_RailDocStudio.bat" "%DEST_DIR%\" >nul
echo       Launcher copied.

echo [8/8] Creating README for end user...
(
echo RailDoc Studio - Gleisplan-Modul v2.0
echo =====================================
echo.
echo INSTALLATION:
echo 1. Extract this folder to any location ^(e.g., Desktop^)
echo 2. Double-click "Start_RailDocStudio.bat" to start
echo.
echo FIRST RUN NOTE:
echo - The first time you run the app, it may take 1-2 minutes to start
echo - PaddleOCR downloads language models ^(~200 MB^) automatically
echo - This only happens once - subsequent starts are fast
echo.
echo YOUR DATA:
echo - All your work is saved in the "RailDocStudio_Data" folder
echo - Keep this folder if you move the application
echo.
echo REQUIREMENTS:
echo - Windows 10 or 11 ^(64-bit^)
echo - 8 GB RAM minimum ^(16 GB recommended^)
echo - 5 GB free disk space
echo.
echo Developed by: Utkarsh Swain
echo Siemens Mobility GmbH, 2026
) > "%DEST_DIR%\README.txt"
echo       README created.

echo.
echo ============================================================
echo    BUILD COMPLETE!
echo ============================================================
echo.
echo Portable distribution created at:
echo    %DEST_DIR%
echo.
echo To test it yourself:
echo    1. Open the folder: %DEST_DIR%
echo    2. Double-click "Start_RailDocStudio.bat"
echo    3. The application should start
echo.
echo To create ZIP for distribution:
echo    Run: build_zip.bat
echo.
pause
