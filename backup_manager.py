"""Backup orchestration and management with deduplication support."""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

import requests
from tqdm import tqdm

from config import BackupConfig
from google_photos_client import GooglePhotosClient
from image_processor import ImageProcessor

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages the backup process with deduplication and progress tracking."""

    def __init__(self, config: BackupConfig):
        """Initialize the backup manager."""
        self.config = config
        self.client = GooglePhotosClient(config)
        self.processor = ImageProcessor(config)
        self.backup_path = Path(config.backup_destination)
        self.dedup_db_path = self.backup_path / "metadata" / "deduplication.json"
        self.dedup_db = self._load_deduplication_db()
        self.stats = {
            "total_items": 0,
            "downloaded": 0,
            "skipped_duplicates": 0,
            "processed": 0,
            "errors": 0,
        }

    def run_backup(self, album_id: Optional[str] = None) -> Dict:
        """
        Run the complete backup process.

        Args:
            album_id: Optional album ID to backup specific album

        Returns:
            Dictionary containing backup statistics
        """
        logger.info("Starting Google Photos backup...")

        # Authenticate
        if not self.client.authenticate():
            raise RuntimeError("Failed to authenticate with Google Photos API")

        # Create backup directories
        self._create_backup_directories()

        # Get media items
        logger.info("Retrieving media items from Google Photos...")
        media_items = list(self.client.get_media_items(album_id=album_id))
        self.stats["total_items"] = len(media_items)

        logger.info(f"Found {len(media_items)} media items to process")

        # Process items with progress bar
        with tqdm(total=len(media_items), desc="Backing up photos") as pbar:
            with ThreadPoolExecutor(
                max_workers=self.config.max_concurrent_downloads
            ) as executor:
                # Submit download tasks
                future_to_item = {
                    executor.submit(self._process_media_item, item): item
                    for item in media_items
                }

                # Process completed downloads
                for future in as_completed(future_to_item):
                    item = future_to_item[future]
                    try:
                        result = future.result()
                        if result:
                            self.stats["downloaded"] += 1
                            if result.get("processed"):
                                self.stats["processed"] += 1
                            if result.get("duplicate"):
                                self.stats["skipped_duplicates"] += 1
                        else:
                            self.stats["errors"] += 1
                    except Exception as e:
                        logger.error(
                            f"Error processing {item.get('filename', 'unknown')}: {e}"
                        )
                        self.stats["errors"] += 1

                    pbar.update(1)

        # Save deduplication database
        self._save_deduplication_db()

        # Generate backup report
        self._generate_backup_report()

        logger.info("Backup completed!")
        return self.stats

    def _process_media_item(self, media_item: Dict) -> Optional[Dict]:
        """
        Process a single media item: download and convert if necessary.

        Args:
            media_item: Media item from Google Photos API

        Returns:
            Dictionary with processing results or None if failed
        """
        try:
            download_url, filename = self.client.get_media_item_download_info(
                media_item
            )
            metadata = self.client.get_media_metadata(media_item)

            # Generate optimal filename
            optimal_filename = self.processor.get_optimal_filename(
                filename, metadata.get("creation_time")
            )

            # Determine download path
            photos_dir = self.backup_path / "photos"
            download_path = photos_dir / optimal_filename

            # Check for duplicates if enabled
            if self.config.use_hash_deduplication:
                item_id = media_item.get("id")
                if item_id in self.dedup_db:
                    logger.debug(f"Skipping duplicate: {filename}")
                    return {"duplicate": True}

            # Download file
            success = self._download_file(download_url, download_path)
            if not success:
                return None

            result = {"processed": False, "duplicate": False}

            # Process image if it's an image file
            if self._is_image_file(download_path):
                processed_path = download_path

                # Convert HEIC or optimize if needed
                if self._needs_processing(download_path):
                    processed_path = self._get_processed_path(download_path)
                    if self.processor.process_image(download_path, processed_path):
                        # Remove original if conversion successful and different
                        if processed_path != download_path:
                            download_path.unlink()
                        result["processed"] = True
                    else:
                        processed_path = download_path

                # Calculate hash for deduplication
                if self.config.use_hash_deduplication:
                    file_hash = self.processor.calculate_file_hash(processed_path)
                    self.dedup_db[media_item.get("id")] = {
                        "hash": file_hash,
                        "filename": processed_path.name,
                        "download_time": time.time(),
                    }

            # Save metadata
            self._save_item_metadata(metadata, download_path.stem)

            return result

        except Exception as e:
            logger.error(
                f"Failed to process media item {media_item.get('filename', 'unknown')}: {e}"
            )
            return None

    def _download_file(self, url: str, output_path: Path) -> bool:
        """
        Download a file from URL with retry logic.

        Args:
            url: Download URL
            output_path: Path to save file

        Returns:
            True if download successful, False otherwise
        """
        for attempt in range(self.config.retry_attempts):
            try:
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()

                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(
                        chunk_size=self.config.chunk_size
                    ):
                        if chunk:
                            f.write(chunk)

                logger.debug(f"Downloaded: {output_path.name}")
                return True

            except Exception as e:
                logger.warning(
                    f"Download attempt {attempt + 1} failed for {output_path.name}: {e}"
                )
                if attempt < self.config.retry_attempts - 1:
                    time.sleep(self.config.retry_delay)
                else:
                    logger.error(
                        f"Failed to download {output_path.name} after {self.config.retry_attempts} attempts"
                    )

        return False

    def _is_image_file(self, file_path: Path) -> bool:
        """Check if file is an image based on extension."""
        image_extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".heic",
            ".heif",
            ".webp",
            ".tiff",
            ".bmp",
        }
        return file_path.suffix.lower() in image_extensions

    def _needs_processing(self, file_path: Path) -> bool:
        """Check if file needs processing (conversion or optimization)."""
        extension = file_path.suffix.lower()

        # HEIC files need conversion if enabled
        if extension in {".heic", ".heif"} and self.config.convert_heic:
            return True

        # Other formats might need optimization based on config
        return False

    def _get_processed_path(self, original_path: Path) -> Path:
        """Get the path for processed version of file."""
        if (
            original_path.suffix.lower() in {".heic", ".heif"}
            and self.config.convert_heic
        ):
            return original_path.with_suffix(".jpg")
        return original_path

    def _save_item_metadata(self, metadata: Dict, item_stem: str) -> None:
        """Save metadata for a media item."""
        metadata_dir = self.backup_path / "metadata"
        metadata_file = metadata_dir / f"{item_stem}.json"

        try:
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save metadata for {item_stem}: {e}")

    def _create_backup_directories(self) -> None:
        """Create necessary backup directories."""
        directories = [
            self.backup_path / "photos",
            self.backup_path / "albums",
            self.backup_path / "metadata",
            self.backup_path / "logs",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_deduplication_db(self) -> Dict:
        """Load deduplication database."""
        if self.dedup_db_path.exists():
            try:
                with open(self.dedup_db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load deduplication database: {e}")
        return {}

    def _save_deduplication_db(self) -> None:
        """Save deduplication database."""
        try:
            self.dedup_db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dedup_db_path, "w", encoding="utf-8") as f:
                json.dump(self.dedup_db, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save deduplication database: {e}")

    def _generate_backup_report(self) -> None:
        """Generate and save backup report."""
        report = {
            "timestamp": time.time(),
            "stats": self.stats,
            "config": {
                "backup_destination": str(self.config.backup_destination),
                "convert_heic": self.config.convert_heic,
                "jpeg_quality": self.config.jpeg_quality,
                "use_hash_deduplication": self.config.use_hash_deduplication,
            },
        }

        report_file = (
            self.backup_path / "logs" / f"backup_report_{int(time.time())}.json"
        )
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            logger.info(f"Backup report saved: {report_file}")
        except Exception as e:
            logger.error(f"Failed to save backup report: {e}")

    def get_backup_status(self) -> Dict:
        """Get current backup status and statistics."""
        return {
            "stats": self.stats,
            "dedup_db_size": len(self.dedup_db),
            "backup_path": str(self.backup_path),
        }
