"""Configuration management for Google Photos backup system."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass
class BackupConfig:
    """Configuration settings for the backup system."""

    # Google Photos API
    client_id: str
    client_secret: str
    credentials_file: str = "credentials.json"
    token_file: str = "token.json"

    # Backup Settings
    backup_destination: str = "/mnt/nas/google_photos_backup"
    max_concurrent_downloads: int = 5
    chunk_size: int = 8192
    retry_attempts: int = 3
    retry_delay: int = 5

    # Image Processing
    convert_heic: bool = True
    jpeg_quality: int = 95
    preserve_metadata: bool = True
    preferred_formats: tuple = ("jpg", "jpeg", "png")

    # Deduplication
    use_hash_deduplication: bool = True
    hash_algorithm: str = "sha256"

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Google Photos API credentials are required")

        if not os.path.exists(os.path.dirname(self.backup_destination)):
            raise ValueError(
                f"Backup destination directory does not exist: {self.backup_destination}"
            )

        if self.jpeg_quality < 1 or self.jpeg_quality > 100:
            raise ValueError("JPEG quality must be between 1 and 100")

        if self.max_concurrent_downloads < 1:
            raise ValueError("Max concurrent downloads must be at least 1")


def load_config() -> BackupConfig:
    """Load configuration from environment variables and .env file."""
    load_dotenv()

    return BackupConfig(
        client_id=os.getenv("GOOGLE_PHOTOS_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_PHOTOS_CLIENT_SECRET", ""),
        credentials_file=os.getenv("CREDENTIALS_FILE", "credentials.json"),
        token_file=os.getenv("TOKEN_FILE", "token.json"),
        backup_destination=os.getenv(
            "BACKUP_DESTINATION", "/mnt/nas/google_photos_backup"
        ),
        max_concurrent_downloads=int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "5")),
        chunk_size=int(os.getenv("CHUNK_SIZE", "8192")),
        retry_attempts=int(os.getenv("RETRY_ATTEMPTS", "3")),
        retry_delay=int(os.getenv("RETRY_DELAY", "5")),
        convert_heic=os.getenv("CONVERT_HEIC", "true").lower() == "true",
        jpeg_quality=int(os.getenv("JPEG_QUALITY", "95")),
        preserve_metadata=os.getenv("PRESERVE_METADATA", "true").lower() == "true",
        use_hash_deduplication=os.getenv("USE_HASH_DEDUPLICATION", "true").lower()
        == "true",
        hash_algorithm=os.getenv("HASH_ALGORITHM", "sha256"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=os.getenv("LOG_FILE"),
    )


def create_backup_directories(config: BackupConfig) -> None:
    """Create necessary backup directories if they don't exist."""
    backup_path = Path(config.backup_destination)
    backup_path.mkdir(parents=True, exist_ok=True)

    # Create subdirectories for organized storage
    (backup_path / "photos").mkdir(exist_ok=True)
    (backup_path / "albums").mkdir(exist_ok=True)
    (backup_path / "metadata").mkdir(exist_ok=True)
    (backup_path / "logs").mkdir(exist_ok=True)
