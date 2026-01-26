"""
Auto Updater Module for ZI Background Remover
==============================================
Supports both full updates and sequential patch updates.

Sequential Update Flow:
1. Check version.json for new version and patch chain
2. Build patch path from current version to latest
3. Download patches sequentially
4. Apply all patches in one process
5. Restart application once

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
    """Handles checking, downloading, and installing updates with sequential patch support."""
    
    # Minimum version that supports patch updates
    MIN_SUPPORTED_VERSION = "1.0.5"
    
    def __init__(self, version_url: str, current_version: str, app_folder: str = None):
        """
        Initialize the updater.
        
        Args:
            version_url: URL to the version.json file.
            current_version: The current version string (e.g., "1.0.0").
            app_folder: Path to the application folder for updates.
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
                    'full_url': data.get('full_url', ''),
                    'changelog': data.get('changelog', 'No changelog provided.'),
                    'patches': data.get('patches', []),
                    'min_supported_version': data.get('min_supported_version', self.MIN_SUPPORTED_VERSION)
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
    
    def get_patch_chain(self, update_info: dict) -> list[dict] | None:
        """
        Build a chain of patches from current version to latest.
        
        Args:
            update_info: Update info dict containing 'patches' list and 'version'.
            
        Returns:
            List of patch dicts in order, or None if no valid chain exists.
            
        Example:
            Current: 1.0.5, Latest: 1.0.8
            Returns: [
                {"from": "1.0.5", "to": "1.0.6", "url": "...", "size": 125000},
                {"from": "1.0.6", "to": "1.0.8", "url": "...", "size": 98000}
            ]
        """
        patches = update_info.get('patches', [])
        target_version = update_info.get('version')
        min_supported = update_info.get('min_supported_version', self.MIN_SUPPORTED_VERSION)
        
        if not patches or not target_version:
            return None
        
        # Check if current version is too old for patch updates
        if pkg_version.parse(self.current_version) < pkg_version.parse(min_supported):
            print(f"[Updater] Version {self.current_version} is too old for patch updates (min: {min_supported})")
            return None
        
        # Build patch lookup: from_version -> patch_info
        patch_map = {}
        for patch in patches:
            from_ver = patch.get('from')
            if from_ver:
                patch_map[from_ver] = patch
        
        # Build chain from current to target
        chain = []
        current = self.current_version
        max_iterations = 50  # Safety limit
        
        for _ in range(max_iterations):
            if pkg_version.parse(current) >= pkg_version.parse(target_version):
                break
            
            if current not in patch_map:
                print(f"[Updater] No patch found from version {current}")
                return None
            
            patch = patch_map[current]
            chain.append(patch)
            current = patch.get('to')
            
            if not current:
                return None
        
        if not chain:
            return None
        
        # Verify chain ends at target
        last_patch = chain[-1]
        if last_patch.get('to') != target_version:
            print(f"[Updater] Patch chain doesn't reach target version {target_version}")
            return None
        
        return chain
    
    def get_patch_chain_info(self, chain: list[dict]) -> dict:
        """
        Get information about a patch chain.
        
        Returns:
            Dict with total_size, version_path, changelogs
        """
        total_size = sum(p.get('size', 0) for p in chain)
        version_path = [chain[0].get('from', '?')]
        changelogs = []
        
        for patch in chain:
            version_path.append(patch.get('to', '?'))
            if patch.get('changelog'):
                changelogs.append(f"v{patch.get('to')}: {patch.get('changelog')}")
        
        return {
            'total_size': total_size,
            'version_path': version_path,
            'version_path_str': ' → '.join(version_path),
            'changelogs': changelogs,
            'patch_count': len(chain)
        }
    
    def can_use_sequential_update(self, update_info: dict) -> tuple[bool, list | None, dict | None]:
        """
        Check if sequential patch update is possible.
        
        Returns:
            Tuple of (can_use: bool, patch_chain: list or None, chain_info: dict or None)
        """
        chain = self.get_patch_chain(update_info)
        if chain:
            info = self.get_patch_chain_info(chain)
            return True, chain, info
        return False, None, None
    
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
    
    def download_sequential_patches(self, patch_chain: list[dict], 
                                     progress_callback=None,
                                     step_callback=None) -> list[str] | None:
        """
        Download all patches in the chain sequentially.
        
        Args:
            patch_chain: List of patch dicts with 'url', 'from', 'to' keys
            progress_callback: Called with (downloaded_bytes, total_bytes) for each file
            step_callback: Called with (current_step, total_steps, from_ver, to_ver)
            
        Returns:
            List of downloaded patch file paths, or None on failure
        """
        temp_dir = tempfile.gettempdir()
        patch_dir = os.path.join(temp_dir, "zi_patches")
        
        # Clean up old patches
        if os.path.exists(patch_dir):
            shutil.rmtree(patch_dir)
        os.makedirs(patch_dir)
        
        downloaded_patches = []
        total_steps = len(patch_chain)
        
        for index, patch in enumerate(patch_chain):
            if self._cancel_download:
                return None
            
            from_ver = patch.get('from', '?')
            to_ver = patch.get('to', '?')
            url = patch.get('url')
            
            if not url:
                print(f"[Updater] No URL for patch {from_ver} -> {to_ver}")
                return None
            
            # Notify step progress
            if step_callback:
                step_callback(index + 1, total_steps, from_ver, to_ver)
            
            # Download patch
            patch_filename = f"patch_{from_ver}_to_{to_ver}.zip"
            patch_path = os.path.join(patch_dir, patch_filename)
            
            print(f"[Updater] Downloading patch {index + 1}/{total_steps}: {from_ver} -> {to_ver}")
            
            if not self.download_file(url, patch_path, progress_callback):
                print(f"[Updater] Failed to download patch {from_ver} -> {to_ver}")
                return None
            
            downloaded_patches.append(patch_path)
        
        return downloaded_patches
    
    def download_full_update(self, url: str, progress_callback=None) -> str | None:
        """Download full update zip."""
        temp_dir = tempfile.gettempdir()
        update_path = os.path.join(temp_dir, "zi_full_update.zip")
        
        if self.download_file(url, update_path, progress_callback):
            return update_path
        return None
    
    def apply_sequential_patches(self, patch_files: list[str]):
        """
        Apply multiple patches in sequence.
        Creates a batch script to:
        1. Wait for app to close
        2. Extract each patch in order
        3. Restart app
        """
        if not patch_files or len(patch_files) == 0:
            print("[Updater] No patches to apply")
            return
        
        # Validate all patch files exist and are valid zips
        for patch_path in patch_files:
            if not os.path.exists(patch_path):
                print(f"[Updater] Patch file not found: {patch_path}")
                return
            try:
                with zipfile.ZipFile(patch_path, 'r') as zf:
                    if zf.testzip() is not None:
                        print(f"[Updater] Corrupted patch file: {patch_path}")
                        return
            except zipfile.BadZipFile:
                print(f"[Updater] Invalid zip file: {patch_path}")
                return
        
        # Get paths
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
            app_folder = os.path.dirname(current_exe)
        else:
            current_exe = os.path.abspath(sys.argv[0])
            app_folder = os.path.dirname(current_exe)
        
        exe_name = os.path.basename(current_exe)
        
        # Build extraction commands for each patch
        extract_commands = []
        for i, patch_path in enumerate(patch_files):
            extract_commands.append(f'''
echo Applying patch {i + 1} of {len(patch_files)}...
powershell -Command "Expand-Archive -Path '{patch_path}' -DestinationPath '{app_folder}' -Force"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to apply patch {i + 1}!
    pause
    exit /b 1
)
''')
        
        # Create update script
        batch_path = os.path.join(tempfile.gettempdir(), "zi_sequential_update.bat")
        batch_content = f'''@echo off
echo ========================================
echo ZI Background Remover - Sequential Update
echo ========================================
echo.
echo Applying {len(patch_files)} patches...
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

{"".join(extract_commands)}

echo.
echo ========================================
echo   All patches applied successfully!
echo ========================================
echo.
echo Starting application...
ping 127.0.0.1 -n 2 > nul
start "" "{current_exe}"

echo Cleaning up...
ping 127.0.0.1 -n 2 > nul
rmdir /s /q "{os.path.dirname(patch_files[0])}"
del /f /q "%~f0"
'''
        
        with open(batch_path, 'w', encoding='utf-8') as f:
            f.write(batch_content)
        
        print(f"[Updater] Created sequential update script: {batch_path}")
        
        # Launch updater with UAC prompt
        try:
            import ctypes
            print(f"[Updater] Executing update script as Admin: {batch_path}")
            
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, 
                "runas", 
                "cmd.exe", 
                f'/c "{batch_path}"', 
                None, 
                1  # SW_SHOWNORMAL
            )
            
            if ret <= 32:
                raise Exception(f"ShellExecute failed with return code {ret}")
                
        except Exception as e:
            print(f"[Updater] Failed to elevate, trying normal Popen: {e}")
            subprocess.Popen(
                ['cmd', '/c', batch_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                close_fds=True
            )
        
        # Exit application
        sys.exit(0)
    
    def apply_full_update(self, update_zip_path: str):
        """Apply full update from zip file."""
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
        
        exe_name = os.path.basename(current_exe)
        
        # Create update script
        batch_path = os.path.join(tempfile.gettempdir(), "zi_full_update.bat")
        batch_content = f'''@echo off
echo ========================================
echo ZI Background Remover - Full Update
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
echo   Full update applied successfully!
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
        
        print(f"[Updater] Created full update script: {batch_path}")
        
        # Launch with UAC
        try:
            import ctypes
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "cmd.exe", f'/c "{batch_path}"', None, 1
            )
            if ret <= 32:
                raise Exception(f"ShellExecute failed: {ret}")
        except Exception as e:
            print(f"[Updater] Fallback to normal Popen: {e}")
            subprocess.Popen(['cmd', '/c', batch_path], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
        
        sys.exit(0)
    
    def cancel_download(self):
        """Cancel an ongoing download."""
        self._cancel_download = True
    
    def download_and_apply_async(self, update_info: dict, 
                                  progress_callback=None, 
                                  step_callback=None,
                                  complete_callback=None, 
                                  error_callback=None):
        """
        Download and apply update in background thread.
        Automatically chooses sequential patches or full update.
        
        Args:
            update_info: Dict from check_for_updates()
            progress_callback: Called with (downloaded, total) for each file
            step_callback: Called with (current_step, total_steps, from_ver, to_ver)
            complete_callback: Called with (patch_files_or_path, is_full_update)
            error_callback: Called with error message string
        """
        def worker():
            try:
                # Check if sequential update is possible
                can_use, patch_chain, chain_info = self.can_use_sequential_update(update_info)
                
                if can_use and patch_chain:
                    print(f"[Updater] Using sequential update: {chain_info['version_path_str']}")
                    print(f"[Updater] Total patches: {chain_info['patch_count']}, Total size: {chain_info['total_size']} bytes")
                    
                    patch_files = self.download_sequential_patches(
                        patch_chain, 
                        progress_callback,
                        step_callback
                    )
                    
                    if patch_files and len(patch_files) > 0:
                        if complete_callback:
                            complete_callback(patch_files, False)
                        return
                    else:
                        print("[Updater] Sequential download failed, trying full update...")
                
                # Fallback to full update
                full_url = update_info.get('full_url', '')
                if not full_url:
                    if error_callback:
                        error_callback("No full update URL available and patch update failed.")
                    return
                
                print("[Updater] Using full update...")
                if step_callback:
                    step_callback(1, 1, self.current_version, update_info.get('version', '?'))
                
                full_path = self.download_full_update(
                    full_url, 
                    progress_callback
                )
                
                if full_path:
                    if complete_callback:
                        complete_callback(full_path, True)
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
    print("ZI Updater Module with Sequential Patch Support")
    print("=" * 50)
    print("Features:")
    print("  - Sequential patch updates (1.0.5 -> 1.0.6 -> 1.0.8)")
    print("  - Automatic patch chain detection")
    print("  - Full update fallback for old versions")
    print("  - Single restart after all patches applied")
    print(f"  - Minimum supported version for patches: {Updater.MIN_SUPPORTED_VERSION}")
