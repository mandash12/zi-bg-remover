"""
Auto Updater Module for ZI Background Remover
==============================================
Supports both full updates and delta (incremental) updates.

Delta Update Flow:
1. Check version.json for new version
2. Download remote manifest
3. Compare with local files
4. Download only changed files (patch zip)
5. Apply changes and restart

Usage:
    from updater import Updater
    updater = Updater(
        version_url="https://example.com/version.json",
        current_version="1.0.0",
        app_folder="path/to/app"
    )
"""

import os
import sys
import json
import tempfile
import subprocess
import threading
import hashlib
import zipfile
import shutil
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from packaging import version as pkg_version


class Updater:
    """Handles checking, downloading, and installing updates with delta support."""
    
    def __init__(self, version_url: str, current_version: str, app_folder: str = None):
        """
        Initialize the updater.
        
        Args:
            version_url: URL to the version.json file.
            current_version: The current version string (e.g., "1.0.0").
            app_folder: Path to the application folder for delta updates.
        """
        self.version_url = version_url
        self.current_version = current_version
        self.app_folder = app_folder or self._get_app_folder()
        self._download_thread = None
        self._cancel_download = False
    
    def _get_app_folder(self) -> str:
        """Get the application folder path."""
        if getattr(sys, 'frozen', False):
            # Running as compiled exe
            return os.path.dirname(sys.executable)
        else:
            # Running as script
            return os.path.dirname(os.path.abspath(__file__))
    
    def check_for_updates(self) -> tuple[bool, dict | None]:
        """
        Check if a new version is available.
        
        Returns:
            Tuple of (has_update: bool, info: dict or None).
        """
        try:
            req = Request(self.version_url, headers={'User-Agent': 'ZI-BGRemover-Updater'})
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            remote_version = data.get('version', '0.0.0')
            
            if pkg_version.parse(remote_version) > pkg_version.parse(self.current_version):
                return True, {
                    'version': remote_version,
                    'manifest_url': data.get('manifest_url', ''),
                    'patch_base_url': data.get('patch_base_url', ''),
                    'full_url': data.get('full_url', ''),
                    'changelog': data.get('changelog', 'No changelog provided.'),
                    'min_version_for_patch': data.get('min_version_for_patch', '0.0.0')
                }
            else:
                return False, None
                
        except Exception as e:
            print(f"[Updater] Error checking for updates: {e}")
            return False, None
    
    def _calculate_file_hash(self, filepath: str) -> str:
        """Calculate SHA256 hash of a file."""
        hash_func = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    
    def get_local_manifest(self) -> dict:
        """Generate manifest of local files."""
        manifest = {"files": {}}
        app_path = Path(self.app_folder)
        
        for filepath in app_path.rglob('*'):
            if filepath.is_file():
                rel_path = str(filepath.relative_to(app_path)).replace('\\', '/')
                try:
                    manifest["files"][rel_path] = {
                        "hash": self._calculate_file_hash(str(filepath)),
                        "size": filepath.stat().st_size
                    }
                except Exception:
                    pass
        
        return manifest
    
    def download_manifest(self, manifest_url: str) -> dict | None:
        """Download remote manifest."""
        try:
            req = Request(manifest_url, headers={'User-Agent': 'ZI-BGRemover-Updater'})
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"[Updater] Error downloading manifest: {e}")
            return None
    
    def compare_manifests(self, local: dict, remote: dict) -> dict:
        """Compare local and remote manifests."""
        local_files = local.get("files", {})
        remote_files = remote.get("files", {})
        
        result = {
            "changed": [],
            "new": [],
            "deleted": [],
            "download_size": 0
        }
        
        for filepath, info in remote_files.items():
            if filepath in local_files:
                if local_files[filepath]["hash"] != info["hash"]:
                    result["changed"].append(filepath)
                    result["download_size"] += info["size"]
            else:
                result["new"].append(filepath)
                result["download_size"] += info["size"]
        
        for filepath in local_files:
            if filepath not in remote_files:
                result["deleted"].append(filepath)
        
        return result
    
    def can_use_delta_update(self, update_info: dict) -> bool:
        """Check if delta update is possible."""
        min_version = update_info.get('min_version_for_patch', '0.0.0')
        return pkg_version.parse(self.current_version) >= pkg_version.parse(min_version)
    
    def download_file(self, url: str, dest_path: str, progress_callback=None) -> bool:
        """Download a file with progress callback."""
        self._cancel_download = False
        try:
            req = Request(url, headers={'User-Agent': 'ZI-BGRemover-Updater'})
            with urlopen(req, timeout=300) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                
                with open(dest_path, 'wb') as f:
                    while True:
                        if self._cancel_download:
                            return False
                        
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size > 0:
                            progress_callback(downloaded, total_size)
                
                return True
        except Exception as e:
            print(f"[Updater] Download error: {e}")
            return False
    
    def download_delta_update(self, update_info: dict, progress_callback=None) -> str | None:
        """
        Download delta update (only changed files).
        
        Returns path to downloaded patch zip, or None on failure.
        """
        try:
            # Download remote manifest
            remote_manifest = self.download_manifest(update_info['manifest_url'])
            if not remote_manifest:
                return None
            
            # Get local manifest
            local_manifest = self.get_local_manifest()
            
            # Compare
            changes = self.compare_manifests(local_manifest, remote_manifest)
            
            if not changes["changed"] and not changes["new"]:
                print("[Updater] No files to update.")
                return None
            
            # Construct patch URL
            new_version = update_info['version']
            patch_url = f"{update_info['patch_base_url']}/v{new_version}/patch_{self.current_version}_to_{new_version}.zip"
            
            # Download patch
            temp_dir = tempfile.gettempdir()
            patch_path = os.path.join(temp_dir, f"zi_patch_{new_version}.zip")
            
            print(f"[Updater] Downloading patch: {patch_url}")
            if self.download_file(patch_url, patch_path, progress_callback):
                return patch_path
            
            return None
            
        except Exception as e:
            print(f"[Updater] Delta update error: {e}")
            return None
    
    def download_full_update(self, url: str, progress_callback=None) -> str | None:
        """Download full update zip."""
        temp_dir = tempfile.gettempdir()
        update_path = os.path.join(temp_dir, "zi_full_update.zip")
        
        if self.download_file(url, update_path, progress_callback):
            return update_path
        return None
    
    def apply_update(self, update_zip_path: str, is_full: bool = False):
        """
        Apply update from zip file.
        Creates a batch script to:
        1. Wait for app to close
        2. Extract zip to app folder
        3. Restart app
        """
        if not os.path.exists(update_zip_path):
            print(f"[Updater] Update file not found: {update_zip_path}")
            return
        
        # Get paths
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
            app_folder = os.path.dirname(current_exe)
        else:
            current_exe = os.path.abspath(sys.argv[0])
            app_folder = os.path.dirname(current_exe)
        
        # Create update script
        batch_path = os.path.join(tempfile.gettempdir(), "zi_update.bat")
        
        if is_full:
            # Full update: backup old folder, extract new
            exe_name = os.path.basename(current_exe)
            batch_content = f'''@echo off
echo ========================================
echo ZI Background Remover - Installing Update
echo ========================================
echo.

echo Waiting for application to close...
ping 127.0.0.1 -n 3 > nul

echo Force closing application...
taskkill /F /IM "{exe_name}" 2>nul

echo Waiting for process to fully terminate...
:waitloop
tasklist /FI "IMAGENAME eq {exe_name}" 2>nul | find /i "{exe_name}" >nul
if %ERRORLEVEL%==0 (
    echo   Process still running, waiting...
    ping 127.0.0.1 -n 2 > nul
    goto waitloop
)
echo   Process terminated.

echo.
echo Creating backup...
if exist "{app_folder}_backup" rmdir /s /q "{app_folder}_backup"
rename "{app_folder}" "{os.path.basename(app_folder)}_backup"

echo Extracting update...
powershell -Command "Expand-Archive -Path '{update_zip_path}' -DestinationPath '{os.path.dirname(app_folder)}' -Force"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to extract update!
    echo Restoring backup...
    rename "{os.path.basename(app_folder)}_backup" "{os.path.basename(app_folder)}"
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Update applied successfully!
echo ========================================
echo.
echo Starting application...
ping 127.0.0.1 -n 2 > nul
start "" "{current_exe}"

echo Cleaning up...
ping 127.0.0.1 -n 2 > nul
del /f /q "{update_zip_path}"
del /f /q "%~f0"
'''
        else:
            # Delta update: extract only changed files
            exe_name = os.path.basename(current_exe)
            batch_content = f'''@echo off
echo ========================================
echo ZI Background Remover - Applying Patch
echo ========================================
echo.

echo Waiting for application to close...
ping 127.0.0.1 -n 3 > nul

echo Force closing application...
taskkill /F /IM "{exe_name}" 2>nul

echo Waiting for process to fully terminate...
:waitloop
tasklist /FI "IMAGENAME eq {exe_name}" 2>nul | find /i "{exe_name}" >nul
if %ERRORLEVEL%==0 (
    echo   Process still running, waiting...
    ping 127.0.0.1 -n 2 > nul
    goto waitloop
)
echo   Process terminated.

echo.
echo Applying patch...
powershell -Command "Expand-Archive -Path '{update_zip_path}' -DestinationPath '{app_folder}' -Force"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to apply patch!
    echo Please close all ZI-BGRemover windows and try again.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Patch applied successfully!
echo ========================================
echo.
echo Starting application...
ping 127.0.0.1 -n 2 > nul
start "" "{current_exe}"

echo Cleaning up...
ping 127.0.0.1 -n 2 > nul
del /f /q "{update_zip_path}"
del /f /q "%~f0"
'''
        
        with open(batch_path, 'w', encoding='utf-8') as f:
            f.write(batch_content)
        
        print(f"[Updater] Created update script: {batch_path}")
        
        # Launch updater and exit
        # Launch updater with UAC prompt (Run as Administrator)
        # This is critical for updating apps installed in Program Files
        try:
            import ctypes
            print(f"[Updater] Executing update script as Admin: {batch_path}")
            
            # ShellExecuteW(hwnd, operation, file, parameters, directory, show_cmd)
            # operation "runas" prompts for UAC elevation
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, 
                "runas", 
                "cmd.exe", 
                f'/c "{batch_path}"', 
                None, 
                1 # SW_SHOWNORMAL (show console so user sees progress)
            )
            
            if ret <= 32:
                # If ShellExecute failed, raise exception
                raise Exception(f"ShellExecute failed with return code {ret}")
                
        except Exception as e:
            print(f"[Updater] Failed to elevate, trying normal Popen: {e}")
            # Fallback for non-admin installs or if execution fails
            subprocess.Popen(
                ['cmd', '/c', batch_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                close_fds=True
            )
        
        # Exit application to allow overwrite
        sys.exit(0)
    
    def cancel_download(self):
        """Cancel an ongoing download."""
        self._cancel_download = True
    
    def download_and_apply_async(self, update_info: dict, use_delta: bool = True,
                                  progress_callback=None, complete_callback=None, 
                                  error_callback=None):
        """
        Download and apply update in background thread.
        """
        def worker():
            try:
                update_path = None
                is_full = False
                
                if use_delta and self.can_use_delta_update(update_info):
                    print("[Updater] Attempting delta update...")
                    update_path = self.download_delta_update(update_info, progress_callback)
                
                if not update_path:
                    print("[Updater] Falling back to full update...")
                    update_path = self.download_full_update(
                        update_info['full_url'], 
                        progress_callback
                    )
                    is_full = True
                
                if update_path:
                    if complete_callback:
                        complete_callback(update_path, is_full)
                else:
                    if error_callback:
                        error_callback("Download failed or was cancelled.")
                        
            except Exception as e:
                if error_callback:
                    error_callback(str(e))
        
        self._download_thread = threading.Thread(target=worker, daemon=True)
        self._download_thread.start()


# ==================== QUICK TEST ====================
if __name__ == '__main__':
    print("Updater Module with Delta Update Support")
    print("=" * 50)
    print("Features:")
    print("  - Delta updates (download only changed files)")
    print("  - Full updates (fallback)")
    print("  - Manifest comparison")
    print("  - Async download with progress")
