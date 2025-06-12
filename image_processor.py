"""Image processing utilities for format conversion and optimization."""

import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import Image, ExifTags
from PIL.ExifTags import TAGS
from pillow_heif import register_heif_opener

from config import BackupConfig

# Register HEIF opener to handle HEIC files
register_heif_opener()

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Handles image format conversion and optimization."""

    def __init__(self, config: BackupConfig):
        """Initialize the image processor."""
        self.config = config
        self.supported_formats = {
            ".jpg",
            ".jpeg",
            ".png",
            ".heic",
            ".heif",
            ".webp",
            ".tiff",
            ".bmp",
        }

    def process_image(self, input_path: Path, output_path: Path) -> bool:
        """
        Process an image file: convert format if needed and optimize.

        Args:
            input_path: Path to input image file
            output_path: Path for processed output file

        Returns:
            True if processing successful, False otherwise
        """
        try:
            if not self._is_supported_format(input_path):
                logger.warning(f"Unsupported image format: {input_path.suffix}")
                return False

            # Determine output format
            output_format = self._determine_output_format(input_path)
            if output_format:
                output_path = output_path.with_suffix(f".{output_format.lower()}")

            # Load and process image
            with Image.open(input_path) as img:
                # Preserve metadata if requested
                exif_data = None
                if self.config.preserve_metadata and hasattr(img, "_getexif"):
                    exif_data = img._getexif()

                # Convert format if necessary
                processed_img = self._convert_image_format(img, output_format)

                # Save processed image
                self._save_image(processed_img, output_path, exif_data)

                logger.info(f"Processed image: {input_path.name} -> {output_path.name}")
                return True

        except Exception as e:
            logger.error(f"Failed to process image {input_path}: {e}")
            return False

    def _is_supported_format(self, file_path: Path) -> bool:
        """Check if the file format is supported."""
        return file_path.suffix.lower() in self.supported_formats

    def _determine_output_format(self, input_path: Path) -> Optional[str]:
        """
        Determine the optimal output format for an image.

        Args:
            input_path: Path to input image

        Returns:
            Output format string or None to keep original format
        """
        input_ext = input_path.suffix.lower()

        # Convert HEIC/HEIF to JPEG if requested
        if input_ext in {".heic", ".heif"} and self.config.convert_heic:
            return "JPEG"

        # Keep preferred formats as-is
        if input_ext[1:] in [fmt.lower() for fmt in self.config.preferred_formats]:
            return None

        # Convert other formats to JPEG by default
        if input_ext not in {".jpg", ".jpeg", ".png"}:
            return "JPEG"

        return None

    def _convert_image_format(
        self, img: Image.Image, target_format: Optional[str]
    ) -> Image.Image:
        """
        Convert image to target format.

        Args:
            img: PIL Image object
            target_format: Target format string

        Returns:
            Converted PIL Image object
        """
        if not target_format:
            return img

        # Handle transparency for JPEG conversion
        if target_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            # Create white background for transparent images
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            return background

        # Convert to RGB for JPEG
        if target_format == "JPEG" and img.mode != "RGB":
            return img.convert("RGB")

        return img

    def _save_image(
        self, img: Image.Image, output_path: Path, exif_data: Optional[Dict] = None
    ) -> None:
        """
        Save image with appropriate quality settings.

        Args:
            img: PIL Image object to save
            output_path: Output file path
            exif_data: EXIF metadata to preserve
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        save_kwargs = {}

        # Set format-specific options
        if output_path.suffix.lower() in {".jpg", ".jpeg"}:
            save_kwargs.update(
                {
                    "format": "JPEG",
                    "quality": self.config.jpeg_quality,
                    "optimize": True,
                    "progressive": True,
                }
            )
            if exif_data:
                save_kwargs["exif"] = exif_data

        elif output_path.suffix.lower() == ".png":
            save_kwargs.update(
                {
                    "format": "PNG",
                    "optimize": True,
                }
            )

        img.save(output_path, **save_kwargs)

    def extract_metadata(self, image_path: Path) -> Dict:
        """
        Extract metadata from an image file.

        Args:
            image_path: Path to image file

        Returns:
            Dictionary containing extracted metadata
        """
        metadata = {
            "filename": image_path.name,
            "size_bytes": image_path.stat().st_size,
            "format": None,
            "dimensions": None,
            "exif": {},
        }

        try:
            with Image.open(image_path) as img:
                metadata["format"] = img.format
                metadata["dimensions"] = img.size

                # Extract EXIF data
                if hasattr(img, "_getexif") and img._getexif():
                    exif_data = img._getexif()
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        metadata["exif"][tag] = value

        except Exception as e:
            logger.warning(f"Failed to extract metadata from {image_path}: {e}")

        return metadata

    def calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate hash of file contents for deduplication.

        Args:
            file_path: Path to file

        Returns:
            Hash string
        """
        hash_obj = hashlib.new(self.config.hash_algorithm)

        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(self.config.chunk_size), b""):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return ""

    def get_optimal_filename(
        self, original_filename: str, creation_time: Optional[str] = None
    ) -> str:
        """
        Generate an optimal filename based on creation time and original name.

        Args:
            original_filename: Original filename from Google Photos
            creation_time: ISO creation time string

        Returns:
            Optimized filename
        """
        base_name = Path(original_filename).stem
        extension = Path(original_filename).suffix

        # Use creation time for filename if available
        if creation_time:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
                date_prefix = dt.strftime("%Y%m%d_%H%M%S")
                return f"{date_prefix}_{base_name}{extension}"
            except Exception as e:
                logger.warning(f"Failed to parse creation time {creation_time}: {e}")

        return original_filename

    def is_image_corrupted(self, image_path: Path) -> bool:
        """
        Check if an image file is corrupted.

        Args:
            image_path: Path to image file

        Returns:
            True if corrupted, False if valid
        """
        try:
            with Image.open(image_path) as img:
                img.verify()
            return False
        except Exception as e:
            logger.warning(f"Image appears corrupted: {image_path} - {e}")
            return True
