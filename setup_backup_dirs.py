#!/usr/bin/env python3
"""
Setup script to create the directory structure for Google Photos backup.
Creates all necessary directories and validates permissions.
"""

import os
import sys
from pathlib import Path
import click
from datetime import datetime


def create_directory_structure(base_path: Path) -> bool:
    """
    Create the complete directory structure for Google Photos backup.
    
    Args:
        base_path: The base directory path where backup will be stored
        
    Returns:
        bool: True if successful, False otherwise
    """
    directories = [
        "photos",           # Processed photos (JPEG, PNG)
        "photos/by-year",   # Optional: organized by year
        "videos",           # Video files
        "videos/by-year",   # Optional: organized by year
        "metadata",         # JSON metadata files
        "logs",            # Processing logs
        "temp",            # Temporary extraction directory
        "originals",       # Optional: store HEIC originals
        "duplicates",      # Optional: store detected duplicates
    ]
    
    try:
        # Create base directory if it doesn't exist
        base_path.mkdir(parents=True, exist_ok=True)
        print(f"✓ Base directory: {base_path}")
        
        # Create subdirectories
        for dir_name in directories:
            dir_path = base_path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"✓ Created: {dir_path}")
        
        # Create a README in the base directory
        readme_path = base_path / "README.txt"
        with open(readme_path, 'w') as f:
            f.write(f"""Google Photos Backup Directory
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Directory Structure:
- photos/        : Processed photos (JPEG, PNG)
- videos/        : Video files (MP4, MOV, etc.)
- metadata/      : Original Google Photos metadata (JSON)
- logs/          : Processing logs and reports
- temp/          : Temporary files during processing
- originals/     : Original HEIC files (if preserving)
- duplicates/    : Detected duplicate files

Processing photos with:
- HEIC to JPEG conversion
- Metadata preservation
- Hash-based deduplication
""")
        print(f"✓ Created README: {readme_path}")
        
        # Test write permissions
        test_file = base_path / "test_write.tmp"
        try:
            test_file.touch()
            test_file.unlink()
            print("✓ Write permissions verified")
        except Exception as e:
            print(f"✗ No write permissions: {e}")
            return False
            
        return True
        
    except Exception as e:
        print(f"✗ Error creating directories: {e}")
        return False


def check_disk_space(path: Path, required_gb: int = 10) -> bool:
    """
    Check if there's enough disk space.
    
    Args:
        path: Path to check
        required_gb: Required space in GB
        
    Returns:
        bool: True if enough space available
    """
    try:
        import shutil
        stat = shutil.disk_usage(path)
        free_gb = stat.free / (1024**3)
        total_gb = stat.total / (1024**3)
        used_percent = (stat.used / stat.total) * 100
        
        print(f"\nDisk Space Information:")
        print(f"- Total: {total_gb:.1f} GB")
        print(f"- Free: {free_gb:.1f} GB")
        print(f"- Used: {used_percent:.1f}%")
        
        if free_gb < required_gb:
            print(f"⚠️  Warning: Only {free_gb:.1f} GB free, recommend at least {required_gb} GB")
            return False
        else:
            print(f"✓ Sufficient disk space available")
            return True
            
    except Exception as e:
        print(f"Could not check disk space: {e}")
        return True  # Continue anyway


@click.command()
@click.argument('backup_path', type=click.Path())
@click.option('--check-space', default=10, help='Minimum free space in GB (default: 10)')
def main(backup_path: str, check_space: int):
    """
    Setup directory structure for Google Photos backup.
    
    BACKUP_PATH: Base directory where photos will be backed up
    """
    print("Google Photos Backup Directory Setup")
    print("=" * 40)
    
    base_path = Path(backup_path).resolve()
    
    # Check if path already exists
    if base_path.exists():
        if not click.confirm(f"\nDirectory '{base_path}' already exists. Continue?"):
            print("Setup cancelled.")
            sys.exit(0)
    
    # Create directory structure
    print(f"\nCreating directory structure in: {base_path}")
    if not create_directory_structure(base_path):
        print("\n✗ Setup failed!")
        sys.exit(1)
    
    # Check disk space
    check_disk_space(base_path, check_space)
    
    print("\n✓ Setup complete!")
    print(f"\nYou can now process your Google Takeout archives:")
    print(f"  python main.py /path/to/takeout.zip --output {base_path}")


if __name__ == '__main__':
    main()