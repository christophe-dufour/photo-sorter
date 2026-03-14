# Photo Sorter

AI-powered photo sorting tool that identifies "real photos" and copies them to year-organized folders.

## Features

- **Recursive scanning** of multiple source directories
- **CLIP-based classification** to identify real photos vs screenshots/documents
- **EXIF date extraction** with file modification date fallback
- **Pause/resume** support for long-running operations
- **Duplicate detection** to avoid copying same file twice
- **Dry-run mode** to preview actions before copying

## Installation

```bash
git clone git@github.com:christophe-dufour/photo-sorter.git
cd photo-sorter
pip install -r requirements.txt
```

## Usage

```bash
# Dry run - preview what would be copied
python -m photo_sorter --dry-run \
  --source ~/to_clean \
  --source /path/to/pcloud-mount \
  --dest /path/to/pcloud-mount/My\ Pictures

# Actual copy (will take 11-16 hours for ~19k images)
python -m photo_sorter \
  --source ~/to_clean \
  --source /path/to/pcloud-mount \
  --dest /path/to/pcloud-mount/My\ Pictures

# Resume from previous run
python -m photo_sorter \
  --source ~/to_clean \
  --source /path/to/pcloud-mount \
  --dest /path/to/pcloud-mount/My\ Pictures \
  --resume
```

## How It Works

1. **Scan** - Recursively finds all images in source directories
2. **Pre-filter** - Skips obvious screenshots by filename
3. **Classify** - Uses CLIP to determine if image is a "real photo"
4. **Copy** - Copies real photos to `DEST/[year]/filename.ext`
5. **State** - Saves progress every 100 images for pause/resume

## Project Structure

```
photo_sorter/
├── cli.py         # CLI entry point
├── scanner.py     # Find all images
├── classifier.py  # CLIP classification
├── copier.py      # Copy to year folders
└── state.py       # Pause/resume logic
```

## License

MIT
