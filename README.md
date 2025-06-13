# Google Photos Takeout Processor

A Python tool to process Google Takeout archives and organize your photo library on local/NAS storage with automatic HEIC to JPEG conversion, deduplication, and metadata preservation.

## Why Google Takeout?

As of June 2024, Google has restricted new OAuth clients for the Photos Library API, making direct API access impractical for new users. Google Takeout remains the most reliable way to export your entire photo library.

## Features

- 📦 **Process Google Takeout ZIP archives** efficiently
- 🔄 **HEIC to JPEG conversion** at highest quality (95% default)
- 🗂️ **Smart organization** by date with metadata preservation
- 🔍 **Hash-based deduplication** to prevent duplicate storage
- 📊 **Preserve all metadata** from Google Photos
- 🚀 **Fast processing** with progress tracking
- 📈 **Detailed statistics** on processing results

## Quick Start

### Prerequisites
- Python 3.9+ 
- Google Takeout export of your Photos library
- Local or NAS storage destination

### Step 1: Export from Google Takeout

1. **Go to [Google Takeout](https://takeout.google.com/)**
2. **Deselect all** services
3. **Select only "Google Photos"**
4. **Choose export options:**
   - File type: `.zip`
   - Frequency: Export once
   - File size: 50GB (for easier handling)
5. **Wait for export** (Google will email when ready)
6. **Download all ZIP files** to a local folder

### Step 2: Install and Setup

```bash
# Clone repository
git clone <repository>
cd google-photos-backup

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup backup directory structure
python setup_backup_dirs.py /mnt/nas/photos
```

### Step 3: Process Your Photos

**Process a single Takeout ZIP:**
```bash
python takeout-processor.py path/to/takeout-001.zip --output /mnt/nas/photos
```

**Process multiple ZIP files:**
```bash
python takeout-processor.py path/to/takeout-folder/ --output /mnt/nas/photos
```

**Options:**
- `--convert-heic` / `--no-convert-heic`: Control HEIC conversion (default: convert)
- `--output` / `-o`: Specify output directory (required)

## Output Structure

```
output_directory/
├── photos/           # Processed photos (JPEG, PNG)
│   ├── 20230615_143022_IMG_1234.jpg
│   ├── 20230615_144518_IMG_1235.jpg
│   └── by-year/      # Optional year-based organization
├── videos/           # Video files (MP4, MOV, etc.)
│   ├── 20230615_150123_VID_001.mp4
│   └── by-year/      # Optional year-based organization
├── metadata/         # Original Google Photos metadata
│   ├── 20230615_143022_IMG_1234.json
│   └── ...
├── logs/            # Processing logs and reports
├── temp/            # Temporary extraction space
├── originals/       # Original HEIC files (if preserving)
└── duplicates/      # Detected duplicate files
```

### Filename Format
- Pattern: `YYYYMMDD_HHMMSS_originalname.ext`
- Example: `20230615_143022_IMG_1234.jpg`
- Timestamps extracted from Google metadata or file dates

## Configuration

### Environment Setup

Create a `.env` file for configuration:

```bash
# Output directory for processed photos
BACKUP_DESTINATION=/mnt/nas/google_photos_backup

# HEIC conversion settings
CONVERT_HEIC=true
JPEG_QUALITY=95

# Processing options
USE_HASH_DEDUPLICATION=true
PRESERVE_METADATA=true
```

## Performance & Storage

### Expected Performance
- **Processing speed:** 100-200 photos/minute (depends on size and HEIC conversion)
- **HEIC conversion:** ~2 seconds per image
- **Deduplication:** Prevents duplicate storage across multiple exports
- **Memory usage:** <1GB during normal operation

### Storage Requirements
- **Original photos:** 1:1 with Google Photos storage
- **HEIC to JPEG:** May increase size by 10-30%
- **Metadata:** ~1KB per photo
- **Temporary space:** Equal to largest ZIP file

## Advanced Usage

### Incremental Backups

For ongoing backups after initial export:

1. **Export only recent photos** from Google Takeout (select date range)
2. **Process new export** to same output directory
3. **Deduplication** will skip already processed photos

### Custom Organization

Modify `_get_timestamp()` in `takeout-processor.py` to customize file organization:
- By year/month folders
- By album names
- By camera model

## Development

### Code Quality
```bash
# Format code
black takeout-processor.py

# Lint code
pylint takeout-processor.py

# Run tests
pytest tests/
```

### Contributing
1. Fork repository
2. Create feature branch
3. Follow code standards (Black, Pylint ≥8.0)
4. Add tests for new features
5. Submit pull request

## Troubleshooting

### Common Issues

**"No space left on device" during extraction:**
- Ensure temp directory has space equal to largest ZIP
- Set TMPDIR environment variable to different location

**HEIC conversion errors:**
- Install system dependencies: `apt-get install libheif-dev`
- Update pillow-heif: `pip install --upgrade pillow-heif`

**Missing metadata:**
- Google Takeout sometimes omits JSON files
- Tool falls back to file modification dates

**Slow processing:**
- Disable HEIC conversion if not needed: `--no-convert-heic`
- Process on SSD for faster I/O
- Use smaller Takeout archives (10GB instead of 50GB)

## Docker Usage

### Setup Environment

Create a `.env` file with your paths:
```bash
TAKEOUT_INPUT_PATH=/path/to/your/takeout-downloads
BACKUP_DESTINATION=/path/to/your/nas/photos
TEMP_PATH=/tmp/takeout-processing
```

### Docker Commands

**Setup directories:**
```bash
docker compose run --rm google-photos-takeout python setup_backup_dirs.py /app/output
```

**Process single ZIP file:**
```bash
docker compose run --rm google-photos-takeout python main.py /app/input/takeout-001.zip --output /app/output
```

**Process all ZIP files:**
```bash
docker compose run --rm google-photos-takeout python main.py /app/input --output /app/output
```

**View logs:**
```bash
docker compose logs google-photos-takeout
```

## Directory Setup

Before processing photos, set up the backup directory structure:

```bash
# Setup directory structure and check permissions
python setup_backup_dirs.py /path/to/backup/location

# The script will create:
# - All necessary subdirectories
# - Check disk space
# - Verify write permissions
# - Create a README file
```

## License

Apache License 2.0 - See LICENSE file for details.

## Acknowledgments

Built as a response to Google's Photos Library API restrictions, ensuring users maintain control over their photo libraries.