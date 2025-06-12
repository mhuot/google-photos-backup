#!/usr/bin/env python3
"""
Google Photos Backup Tool

A comprehensive tool to backup Google Photos to local NAS storage with
HEIC conversion and deduplication support.
"""

import logging
import sys
from pathlib import Path

import click

from backup_manager import BackupManager
from config import BackupConfig, load_config, create_backup_directories


def setup_logging(log_level: str, log_file: str = None) -> None:
    """Configure logging for the application."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


@click.group()
@click.option("--config-file", default=".env", help="Configuration file path")
@click.option("--log-level", default="INFO", help="Logging level")
@click.option("--log-file", help="Log file path")
@click.pass_context
def cli(ctx, config_file, log_level, log_file):
    """Google Photos Backup Tool - Backup your Google Photos to local storage."""
    ctx.ensure_object(dict)

    # Setup logging
    setup_logging(log_level, log_file)

    # Load configuration
    try:
        if config_file != ".env":
            import os

            os.environ["DOTENV_PATH"] = config_file

        config = load_config()
        ctx.obj["config"] = config

        # Create backup directories
        create_backup_directories(config)

    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--album-id", help="Specific album ID to backup")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be backed up without downloading"
)
@click.pass_context
def backup(ctx, album_id, dry_run):
    """Start the backup process for Google Photos."""
    config = ctx.obj["config"]

    if dry_run:
        click.echo("DRY RUN MODE - No files will be downloaded")

    try:
        manager = BackupManager(config)

        if dry_run:
            # Authenticate and get item count without downloading
            if not manager.client.authenticate():
                click.echo("Authentication failed", err=True)
                sys.exit(1)

            media_items = list(manager.client.get_media_items(album_id=album_id))
            click.echo(f"Would backup {len(media_items)} media items")

            if album_id:
                click.echo(f"From album ID: {album_id}")

            click.echo(f"To destination: {config.backup_destination}")
            return

        # Run actual backup
        click.echo("Starting Google Photos backup...")
        stats = manager.run_backup(album_id=album_id)

        # Display results
        click.echo("\n" + "=" * 50)
        click.echo("BACKUP COMPLETED")
        click.echo("=" * 50)
        click.echo(f"Total items found: {stats['total_items']}")
        click.echo(f"Successfully downloaded: {stats['downloaded']}")
        click.echo(f"Processed (converted): {stats['processed']}")
        click.echo(f"Skipped (duplicates): {stats['skipped_duplicates']}")
        click.echo(f"Errors: {stats['errors']}")
        click.echo(f"Backup location: {config.backup_destination}")

    except KeyboardInterrupt:
        click.echo("\nBackup interrupted by user")
        sys.exit(1)
    except Exception as e:
        click.echo(f"Backup failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def albums(ctx):
    """List all available albums in Google Photos."""
    config = ctx.obj["config"]

    try:
        manager = BackupManager(config)

        if not manager.client.authenticate():
            click.echo("Authentication failed", err=True)
            sys.exit(1)

        click.echo("Retrieving albums...")
        albums_list = manager.client.get_albums()

        if not albums_list:
            click.echo("No albums found")
            return

        click.echo(f"\nFound {len(albums_list)} albums:")
        click.echo("-" * 60)

        for album in albums_list:
            album_id = album.get("id", "N/A")
            title = album.get("title", "Untitled")
            item_count = album.get("mediaItemsCount", "Unknown")

            click.echo(f"ID: {album_id}")
            click.echo(f"Title: {title}")
            click.echo(f"Items: {item_count}")
            click.echo("-" * 60)

    except Exception as e:
        click.echo(f"Failed to retrieve albums: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx):
    """Show backup status and statistics."""
    config = ctx.obj["config"]
    backup_path = Path(config.backup_destination)

    click.echo("GOOGLE PHOTOS BACKUP STATUS")
    click.echo("=" * 40)

    # Configuration info
    click.echo(f"Backup destination: {config.backup_destination}")
    click.echo(f"HEIC conversion: {'Enabled' if config.convert_heic else 'Disabled'}")
    click.echo(f"JPEG quality: {config.jpeg_quality}%")
    click.echo(
        f"Deduplication: {'Enabled' if config.use_hash_deduplication else 'Disabled'}"
    )

    # Directory stats
    if backup_path.exists():
        photos_dir = backup_path / "photos"
        metadata_dir = backup_path / "metadata"
        logs_dir = backup_path / "logs"

        photo_count = len(list(photos_dir.glob("*"))) if photos_dir.exists() else 0
        metadata_count = (
            len(list(metadata_dir.glob("*.json"))) if metadata_dir.exists() else 0
        )
        log_count = len(list(logs_dir.glob("*.json"))) if logs_dir.exists() else 0

        click.echo(f"\nBacked up photos: {photo_count}")
        click.echo(f"Metadata files: {metadata_count}")
        click.echo(f"Backup reports: {log_count}")

        # Recent backup info
        if logs_dir.exists():
            recent_reports = sorted(logs_dir.glob("backup_report_*.json"), reverse=True)
            if recent_reports:
                import json

                try:
                    with open(recent_reports[0], "r") as f:
                        report = json.load(f)

                    from datetime import datetime

                    backup_time = datetime.fromtimestamp(report["timestamp"])
                    click.echo(
                        f"Last backup: {backup_time.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                except Exception:
                    pass
    else:
        click.echo("\nNo backup directory found")


@cli.command()
@click.confirmation_option(prompt="Are you sure you want to reset authentication?")
@click.pass_context
def reset_auth(ctx):
    """Reset Google Photos authentication credentials."""
    config = ctx.obj["config"]

    token_file = Path(config.token_file)
    if token_file.exists():
        token_file.unlink()
        click.echo(f"Removed token file: {token_file}")

    click.echo("Authentication reset. Run backup command to re-authenticate.")


@cli.command()
@click.option("--destination", required=True, help="NAS backup destination path")
@click.option("--client-id", required=True, help="Google Photos API client ID")
@click.option("--client-secret", required=True, help="Google Photos API client secret")
@click.pass_context
def setup(ctx, destination, client_id, client_secret):
    """Initial setup wizard for Google Photos backup."""
    click.echo("GOOGLE PHOTOS BACKUP SETUP")
    click.echo("=" * 40)

    # Validate destination
    dest_path = Path(destination)
    if not dest_path.parent.exists():
        click.echo(
            f"Error: Parent directory does not exist: {dest_path.parent}", err=True
        )
        sys.exit(1)

    # Create .env file
    env_content = f"""# Google Photos Backup Configuration
GOOGLE_PHOTOS_CLIENT_ID={client_id}
GOOGLE_PHOTOS_CLIENT_SECRET={client_secret}
BACKUP_DESTINATION={destination}

# Optional settings (uncomment to modify)
# CONVERT_HEIC=true
# JPEG_QUALITY=95
# MAX_CONCURRENT_DOWNLOADS=5
# USE_HASH_DEDUPLICATION=true
# LOG_LEVEL=INFO
"""

    env_file = Path(".env")
    with open(env_file, "w") as f:
        f.write(env_content)

    click.echo(f"Configuration saved to: {env_file.absolute()}")
    click.echo("Setup complete! You can now run: python main.py backup")


if __name__ == "__main__":
    cli()
