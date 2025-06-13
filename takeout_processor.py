#!/usr/bin/env python3
"""
Google Takeout Photo Processor
Processes Google Takeout archives and organizes photos on NAS
"""

import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set
import hashlib
import click
from PIL import Image
from pillow_heif import register_heif_opener
from tqdm import tqdm

# Register HEIF support
register_heif_opener()


class TakeoutProcessor:
    def __init__(self, output_dir: Path, convert_heic: bool = True):
        self.output_dir = Path(output_dir)
        self.convert_heic = convert_heic
        self.processed_hashes: Set[str] = set()
        self.stats = {
            "total_files": 0,
            "processed": 0,
            "duplicates": 0,
            "converted": 0,
            "errors": 0
        }
        
        # Create output directories
        (self.output_dir / "photos").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "videos").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "metadata").mkdir(parents=True, exist_ok=True)

    def process_takeout_zip(self, zip_path: Path) -> None:
        """Extract and process a Google Takeout ZIP file."""
        print(f"Processing {zip_path.name}...")
        
        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            # Extract to temporary directory
            temp_dir = Path(f"/tmp/takeout_{datetime.now().timestamp()}")
            zip_file.extractall(temp_dir)
            
            # Find all media files
            media_files = []
            for pattern in ["*.jpg", "*.jpeg", "*.png", "*.heic", "*.heif", "*.mp4", "*.mov"]:
                media_files.extend(temp_dir.rglob(pattern))
            
            self.stats["total_files"] = len(media_files)
            
            # Process each file
            for media_file in tqdm(media_files, desc="Processing files"):
                self._process_media_file(media_file)
            
            # Cleanup
            shutil.rmtree(temp_dir)

    def _process_media_file(self, file_path: Path) -> None:
        """Process a single media file."""
        try:
            # Look for associated JSON metadata
            json_path = file_path.with_suffix(file_path.suffix + ".json")
            metadata = self._load_metadata(json_path) if json_path.exists() else {}
            
            # Calculate file hash for deduplication
            file_hash = self._calculate_hash(file_path)
            if file_hash in self.processed_hashes:
                self.stats["duplicates"] += 1
                return
            
            # Determine output path
            timestamp = self._get_timestamp(metadata, file_path)
            is_video = file_path.suffix.lower() in ['.mp4', '.mov', '.avi']
            
            if is_video:
                output_dir = self.output_dir / "videos"
            else:
                output_dir = self.output_dir / "photos"
            
            # Generate filename with date prefix
            date_prefix = timestamp.strftime("%Y%m%d_%H%M%S")
            output_filename = f"{date_prefix}_{file_path.stem}{file_path.suffix}"
            output_path = output_dir / output_filename
            
            # Handle HEIC conversion
            if self.convert_heic and file_path.suffix.lower() in ['.heic', '.heif']:
                output_path = output_path.with_suffix('.jpg')
                self._convert_heic_to_jpg(file_path, output_path)
                self.stats["converted"] += 1
            else:
                # Copy file
                shutil.copy2(file_path, output_path)
            
            # Save metadata
            if metadata:
                meta_path = self.output_dir / "metadata" / f"{output_path.stem}.json"
                with open(meta_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
            
            self.processed_hashes.add(file_hash)
            self.stats["processed"] += 1
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            self.stats["errors"] += 1

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _load_metadata(self, json_path: Path) -> Dict:
        """Load metadata from JSON file."""
        try:
            with open(json_path, 'r') as f:
                return json.load(f)
        except:
            return {}

    def _get_timestamp(self, metadata: Dict, file_path: Path) -> datetime:
        """Extract timestamp from metadata or file."""
        # Try metadata first
        if metadata.get('photoTakenTime', {}).get('timestamp'):
            return datetime.fromtimestamp(
                int(metadata['photoTakenTime']['timestamp'])
            )
        elif metadata.get('creationTime', {}).get('timestamp'):
            return datetime.fromtimestamp(
                int(metadata['creationTime']['timestamp'])
            )
        
        # Fall back to file modification time
        return datetime.fromtimestamp(file_path.stat().st_mtime)

    def _convert_heic_to_jpg(self, input_path: Path, output_path: Path) -> None:
        """Convert HEIC image to JPEG."""
        image = Image.open(input_path)
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Save as JPEG with high quality
        image.save(output_path, 'JPEG', quality=95, optimize=True)

    def print_stats(self) -> None:
        """Print processing statistics."""
        print("\n" + "="*50)
        print("PROCESSING COMPLETE")
        print("="*50)
        print(f"Total files found: {self.stats['total_files']}")
        print(f"Successfully processed: {self.stats['processed']}")
        print(f"Duplicates skipped: {self.stats['duplicates']}")
        print(f"HEIC files converted: {self.stats['converted']}")
        print(f"Errors: {self.stats['errors']}")


@click.command()
@click.argument('takeout_path', type=click.Path(exists=True))
@click.option('--output', '-o', required=True, help='Output directory path')
@click.option('--convert-heic/--no-convert-heic', default=True, 
              help='Convert HEIC files to JPEG')
def main(takeout_path: str, output: str, convert_heic: bool):
    """Process Google Takeout archives and organize photos."""
    takeout_path = Path(takeout_path)
    output_dir = Path(output)
    
    processor = TakeoutProcessor(output_dir, convert_heic)
    
    if takeout_path.is_file() and takeout_path.suffix == '.zip':
        # Single ZIP file
        processor.process_takeout_zip(takeout_path)
    elif takeout_path.is_dir():
        # Directory containing multiple ZIP files
        zip_files = list(takeout_path.glob('*.zip'))
        print(f"Found {len(zip_files)} ZIP files to process")
        
        for zip_file in zip_files:
            processor.process_takeout_zip(zip_file)
    else:
        print("Please provide a ZIP file or directory containing ZIP files")
        return
    
    processor.print_stats()


if __name__ == '__main__':
    main()
