"""Google Photos API client for authentication and photo retrieval."""

import json
import logging
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import google.auth.exceptions
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import BackupConfig

logger = logging.getLogger(__name__)

# Google Photos API scope
SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly"]


class GooglePhotosClient:
    """Client for interacting with Google Photos API."""

    def __init__(self, config: BackupConfig):
        """Initialize the Google Photos client."""
        self.config = config
        self.service = None
        self.credentials = None

    def authenticate(self) -> bool:
        """Authenticate with Google Photos API using OAuth2."""
        try:
            self.credentials = self._load_or_create_credentials()
            self.service = build("photoslibrary", "v1", credentials=self.credentials)
            logger.info("Successfully authenticated with Google Photos API")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def _load_or_create_credentials(self) -> Credentials:
        """Load existing credentials or create new ones through OAuth flow."""
        token_path = Path(self.config.token_file)
        credentials_path = Path(self.config.credentials_file)

        credentials = None

        # Load existing token if available
        if token_path.exists():
            try:
                credentials = Credentials.from_authorized_user_file(
                    str(token_path), SCOPES
                )
                logger.info("Loaded existing credentials")
            except Exception as e:
                logger.warning(f"Failed to load existing credentials: {e}")

        # Refresh expired credentials
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                logger.info("Refreshed expired credentials")
            except google.auth.exceptions.RefreshError as e:
                logger.warning(f"Failed to refresh credentials: {e}")
                credentials = None

        # Create new credentials if needed
        if not credentials or not credentials.valid:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"Credentials file not found: {credentials_path}. "
                    "Please download it from Google Cloud Console."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            credentials = flow.run_local_server(port=0)
            logger.info("Created new credentials through OAuth flow")

        # Save credentials for future use
        with open(token_path, "w", encoding="utf-8") as token:
            token.write(credentials.to_json())

        return credentials

    def get_media_items(
        self, page_size: int = 100, album_id: Optional[str] = None
    ) -> Iterator[Dict]:
        """
        Retrieve media items from Google Photos.

        Args:
            page_size: Number of items to retrieve per page (max 100)
            album_id: Optional album ID to retrieve items from specific album

        Yields:
            Dictionary containing media item information
        """
        if not self.service:
            raise RuntimeError("Client not authenticated. Call authenticate() first.")

        page_token = None
        total_items = 0

        try:
            while True:
                request_body = {"pageSize": min(page_size, 100)}

                if album_id:
                    request_body["albumId"] = album_id

                if page_token:
                    request_body["pageToken"] = page_token

                response = self.service.mediaItems().list(**request_body).execute()

                media_items = response.get("mediaItems", [])
                if not media_items:
                    break

                for item in media_items:
                    total_items += 1
                    yield item

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

                if total_items % 1000 == 0:
                    logger.info(f"Retrieved {total_items} media items so far...")

        except HttpError as e:
            logger.error(f"HTTP error retrieving media items: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving media items: {e}")
            raise

        logger.info(f"Retrieved total of {total_items} media items")

    def get_albums(self) -> List[Dict]:
        """Retrieve all albums from Google Photos."""
        if not self.service:
            raise RuntimeError("Client not authenticated. Call authenticate() first.")

        albums = []
        page_token = None

        try:
            while True:
                request_body = {"pageSize": 50}
                if page_token:
                    request_body["pageToken"] = page_token

                response = self.service.albums().list(**request_body).execute()

                album_list = response.get("albums", [])
                if not album_list:
                    break

                albums.extend(album_list)
                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            logger.info(f"Retrieved {len(albums)} albums")
            return albums

        except HttpError as e:
            logger.error(f"HTTP error retrieving albums: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving albums: {e}")
            raise

    def get_media_item_download_info(self, media_item: Dict) -> Tuple[str, str]:
        """
        Extract download URL and filename from media item.

        Args:
            media_item: Media item dictionary from Google Photos API

        Returns:
            Tuple of (download_url, filename)
        """
        base_url = media_item.get("baseUrl", "")
        filename = media_item.get("filename", "unknown")

        # Request highest quality download
        # For photos: =d (original), =w4000-h4000 (high resolution)
        # For videos: =dv (original)
        mime_type = media_item.get("mimeType", "")

        if mime_type.startswith("video/"):
            download_url = f"{base_url}=dv"
        else:
            download_url = f"{base_url}=d"

        return download_url, filename

    def get_media_metadata(self, media_item: Dict) -> Dict:
        """Extract metadata from media item."""
        metadata = {
            "id": media_item.get("id"),
            "filename": media_item.get("filename"),
            "mime_type": media_item.get("mimeType"),
            "creation_time": media_item.get("mediaMetadata", {}).get("creationTime"),
            "width": media_item.get("mediaMetadata", {}).get("width"),
            "height": media_item.get("mediaMetadata", {}).get("height"),
            "description": media_item.get("description", ""),
        }

        # Extract photo-specific metadata
        photo_metadata = media_item.get("mediaMetadata", {}).get("photo", {})
        if photo_metadata:
            metadata.update(
                {
                    "camera_make": photo_metadata.get("cameraMake"),
                    "camera_model": photo_metadata.get("cameraModel"),
                    "focal_length": photo_metadata.get("focalLength"),
                    "aperture_f_number": photo_metadata.get("apertureFNumber"),
                    "iso_equivalent": photo_metadata.get("isoEquivalent"),
                    "exposure_time": photo_metadata.get("exposureTime"),
                }
            )

        return metadata
