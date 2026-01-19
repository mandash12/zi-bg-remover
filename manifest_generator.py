"""
Manifest Generator for Delta Updates
======================================
Generates a JSON manifest containing SHA256 hashes of all files in the application folder.
Used for comparing local vs remote files to determine what needs updating.

Usage:
    python manifest_generator.py <app_folder> <version> [output_file]
    
Example:
    python manifest_generator.py dist/ZI-BGRemover 1.0.0 manifest_v1.0.0.json
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime


def calculate_file_hash(filepath: str, algorithm: str = 'sha256') -> str:
    """Calculate hash of a file."""
    hash_func = hashlib.new(algorithm)
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def generate_manifest(app_folder: str, version: str) -> dict:
    """
    Generate a manifest of all files in the application folder.
    
    Args:
        app_folder: Path to the application folder (e.g., dist/ZI-BGRemover)
        version: Version string (e.g., "1.0.0")
    
    Returns:
        Dictionary containing version and file hashes
    """
    app_path = Path(app_folder)
    
    if not app_path.exists():
        raise FileNotFoundError(f"Application folder not found: {app_folder}")
    
    manifest = {
        "version": version,
        "generated": datetime.now().isoformat(),
        "files": {}
    }
    
    # Walk through all files
    for filepath in app_path.rglob('*'):
        if filepath.is_file():
            # Get relative path from app folder
            rel_path = filepath.relative_to(app_path)
            # Use forward slashes for consistency
            rel_path_str = str(rel_path).replace('\\', '/')
            
            # Calculate hash
            file_hash = calculate_file_hash(str(filepath))
            file_size = filepath.stat().st_size
            
            manifest["files"][rel_path_str] = {
                "hash": file_hash,
                "size": file_size
            }
    
    manifest["total_files"] = len(manifest["files"])
    manifest["total_size"] = sum(f["size"] for f in manifest["files"].values())
    
    return manifest


def compare_manifests(local_manifest: dict, remote_manifest: dict) -> dict:
    """
    Compare local and remote manifests to find changed/new/deleted files.
    
    Returns:
        Dictionary with 'changed', 'new', 'deleted' lists of file paths
    """
    local_files = local_manifest.get("files", {})
    remote_files = remote_manifest.get("files", {})
    
    result = {
        "changed": [],  # Files that exist in both but have different hashes
        "new": [],      # Files in remote but not in local
        "deleted": []   # Files in local but not in remote
    }
    
    # Find changed and new files
    for filepath, info in remote_files.items():
        if filepath in local_files:
            if local_files[filepath]["hash"] != info["hash"]:
                result["changed"].append(filepath)
        else:
            result["new"].append(filepath)
    
    # Find deleted files
    for filepath in local_files:
        if filepath not in remote_files:
            result["deleted"].append(filepath)
    
    return result


def main():
    if len(sys.argv) < 3:
        print("Usage: python manifest_generator.py <app_folder> <version> [output_file]")
        print("Example: python manifest_generator.py dist/ZI-BGRemover 1.0.0")
        sys.exit(1)
    
    app_folder = sys.argv[1]
    version = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else f"manifest_v{version}.json"
    
    print(f"Generating manifest for {app_folder} v{version}...")
    
    try:
        manifest = generate_manifest(app_folder, version)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"✓ Manifest generated: {output_file}")
        print(f"  Total files: {manifest['total_files']}")
        print(f"  Total size: {manifest['total_size'] / (1024*1024*1024):.2f} GB")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
