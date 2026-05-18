@echo off
setlocal

REM â”€â”€ build_exe.bat â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
REM Builds PriceValidation.exe (onedir) and packages it as a zip for release.
REM  - Builds to C:\Temp\PVTool\dist  (avoids OneDrive WinError 5)
REM  - Copies result back to dist\PriceValidation\
REM  - Creates dist\PriceValidation-v<version>.zip
REM â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

set VERSION=1.3.0
set BUILD_DIR=C:\Temp\PVTool
set PROJECT_DIR=%~dp0

echo [1/5] Installing dependencies...
poetry install
if errorlevel 1 ( echo ERROR: poetry install failed & exit /b 1 )

echo [2/5] Building with PyInstaller (output to %BUILD_DIR%)...
if not exist %BUILD_DIR% mkdir %BUILD_DIR%
poetry run pyinstaller PriceValidation.spec --distpath "%BUILD_DIR%\dist" --workpath "%BUILD_DIR%\build" --noconfirm
if errorlevel 1 ( echo ERROR: PyInstaller failed & exit /b 1 )

echo [3/5] Copying dist back to project...
if exist "%PROJECT_DIR%dist" rmdir /s /q "%PROJECT_DIR%dist"
xcopy /e /i "%BUILD_DIR%\dist" "%PROJECT_DIR%dist"
if errorlevel 1 ( echo ERROR: xcopy failed & exit /b 1 )

echo [4/5] Creating zip archive...
set ZIP_NAME=PriceValidation-v%VERSION%.zip
if exist "%PROJECT_DIR%%ZIP_NAME%" del "%PROJECT_DIR%%ZIP_NAME%"
powershell -NoProfile -Command "Compress-Archive -Path '%PROJECT_DIR%dist\PriceValidation\*' -DestinationPath '%PROJECT_DIR%%ZIP_NAME%'"
if errorlevel 1 ( echo ERROR: zip failed & exit /b 1 )

echo [5/5] Done!
echo   Exe  : dist\PriceValidation\PriceValidation.exe
echo   Zip  : %ZIP_NAME%
echo.
echo To create a GitHub release:
echo   gh release create v%VERSION% %ZIP_NAME% --title "v%VERSION%" --notes "Release v%VERSION%"

endlocal

