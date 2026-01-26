@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   ZI Background Remover - Release Tool
echo ========================================
echo.

:: Check if version argument is provided
if "%~1"=="" (
    echo Usage: release.bat ^<new_version^> ^<old_version^> [changelog]
    echo Example: release.bat 1.0.8 1.0.7 "Fix bug dan update UI"
    echo.
    echo This script will:
    echo   1. Build the application using PyInstaller
    echo   2. Apply PyArmor protection
    echo   3. Generate manifest for new version
    echo   4. Create patch from old version to new version
    echo   5. Update version.json with sequential patches
    echo   6. Create portable ZIP
    echo   7. Create installer (Inno Setup)
    echo   8. Push changes to GitHub
    echo.
    pause
    exit /b 1
)

set NEW_VERSION=%~1
set OLD_VERSION=%~2
set CHANGELOG=%~3

if "%OLD_VERSION%"=="" (
    echo ERROR: Please provide both new and old version numbers!
    echo Example: release.bat 1.0.8 1.0.7 "Fix dan update baru"
    pause
    exit /b 1
)

:: Default changelog if not provided
if "%CHANGELOG%"=="" (
    set CHANGELOG=v%NEW_VERSION% - Update
)

echo New Version: %NEW_VERSION%
echo Old Version: %OLD_VERSION%
echo Changelog  : %CHANGELOG%
echo.
echo Press any key to start the release process...
pause > nul

:: Step 1: PyInstaller
echo.
echo [1/8] Building with PyInstaller...
echo ========================================
pyinstaller --noconfirm --onedir --windowed --name "ZI-BGRemover" --icon "icon.ico" --add-data "header_logo.png;." --add-data "icon.png;." --add-data "splash.jpg;." app_hapus_bg.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyInstaller failed!
    pause
    exit /b 1
)
echo [OK] PyInstaller completed.

:: Step 2: PyArmor
echo.
echo [2/8] Applying PyArmor protection...
echo ========================================
pyarmor gen --output "dist\ZI-BGRemover\_internal" license_manager.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyArmor failed!
    pause
    exit /b 1
)
echo [OK] PyArmor completed.

:: Step 3: Manifest Generator
echo.
echo [3/8] Generating manifest v%NEW_VERSION%...
echo ========================================
python manifest_generator.py "dist\ZI-BGRemover" %NEW_VERSION%
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Manifest generator failed!
    pause
    exit /b 1
)
echo [OK] Manifest generated.

:: Step 4: Create Patch
echo.
echo [4/8] Creating patch %OLD_VERSION% -^> %NEW_VERSION%...
echo ========================================
python create_patch.py %OLD_VERSION% %NEW_VERSION%
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Patch creation failed!
    pause
    exit /b 1
)
echo [OK] Patch created.

:: Step 5: Create Full Portable ZIP
echo.
echo [5/8] Creating Full Portable ZIP...
echo ========================================
powershell -Command "Compress-Archive -Path 'dist\ZI-BGRemover' -DestinationPath 'ZI-BGRemover-v%NEW_VERSION%-Portable.zip' -Force"
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Failed to create portable ZIP.
) else (
    echo [OK] Portable ZIP created: ZI-BGRemover-v%NEW_VERSION%-Portable.zip
)

:: Step 6: Update version.json with sequential patches
echo.
echo [6/8] Updating version.json with sequential patches...
echo ========================================

:: Get the old patch file size if it exists
set PATCH_SIZE=0
for %%A in (patch_%OLD_VERSION%_to_%NEW_VERSION%.zip) do set PATCH_SIZE=%%~zA

python -c "
import json
import os

# Load existing version.json if exists
existing_patches = []
try:
    with open('version.json', 'r') as f:
        old_data = json.load(f)
        existing_patches = old_data.get('patches', [])
except:
    pass

# Add new patch to the chain
new_patch = {
    'from': '%OLD_VERSION%',
    'to': '%NEW_VERSION%',
    'url': 'https://github.com/mandash12/zi-bg-remover/releases/download/v%NEW_VERSION%/patch_%OLD_VERSION%_to_%NEW_VERSION%.zip',
    'size': %PATCH_SIZE%,
    'changelog': '%CHANGELOG%'
}

# Check if patch already exists, update if so
patch_exists = False
for i, p in enumerate(existing_patches):
    if p.get('from') == '%OLD_VERSION%' and p.get('to') == '%NEW_VERSION%':
        existing_patches[i] = new_patch
        patch_exists = True
        break

if not patch_exists:
    existing_patches.append(new_patch)

# Create new version.json
data = {
    'version': '%NEW_VERSION%',
    'full_url': 'https://github.com/mandash12/zi-bg-remover/releases/download/v%NEW_VERSION%/ZI-BGRemover-v%NEW_VERSION%-Portable.zip',
    'changelog': '%CHANGELOG%',
    'min_supported_version': '1.0.5',
    'patches': existing_patches
}

with open('version.json', 'w') as f:
    json.dump(data, f, indent=4)

print('[OK] version.json updated with sequential patches.')
"
echo [OK] version.json updated.

:: Step 7: Build Installer with Inno Setup
echo.
echo [7/8] Building Installer with Inno Setup...
echo ========================================
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss
    if %ERRORLEVEL% NEQ 0 (
        echo WARNING: Inno Setup failed. Installer not created.
    ) else (
        echo [OK] Installer created: installer\output\ZI-BGRemover-Setup-v%NEW_VERSION%.exe
    )
) else (
    echo WARNING: Inno Setup not found. Skipping installer creation.
    echo Install from: https://jrsoftware.org/isinfo.php
)

:: Step 8: Git Push
echo.
echo [8/8] Pushing to GitHub...
echo ========================================
git add version.json manifest_v%NEW_VERSION%.json app_hapus_bg.py updater.py license_dialog.py installer\setup.iss
git commit -m "Release v%NEW_VERSION% - %CHANGELOG%"
git push
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Git push may have failed. Check manually.
)
echo [OK] Pushed to GitHub.

:: Summary
echo.
echo ========================================
echo   RELEASE v%NEW_VERSION% COMPLETE!
echo ========================================
echo.
echo Files created:
echo   - dist\ZI-BGRemover\ (built application)
echo   - manifest_v%NEW_VERSION%.json (file hashes)
echo   - patch_%OLD_VERSION%_to_%NEW_VERSION%.zip (delta update)
echo   - ZI-BGRemover-v%NEW_VERSION%-Portable.zip (full portable)
echo   - installer\output\ZI-BGRemover-Setup-v%NEW_VERSION%.exe (installer)
echo.
echo NEXT STEPS:
echo   1. Go to: https://github.com/mandash12/zi-bg-remover/releases
echo   2. Create new release with tag: v%NEW_VERSION%
echo   3. Upload these files:
echo      - patch_%OLD_VERSION%_to_%NEW_VERSION%.zip
echo      - ZI-BGRemover-v%NEW_VERSION%-Portable.zip
echo      - installer\output\ZI-BGRemover-Setup-v%NEW_VERSION%.exe
echo   4. Publish release
echo.
echo Your users can now update automatically with sequential patches!
echo.
pause
