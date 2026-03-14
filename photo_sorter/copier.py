"""Copier module - handles copying photos to year-organized folders."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image
from PIL.ExifTags import TAGS


def extract_exif_date(image_path: Path) -> Optional[datetime]:
    """Extract date taken from EXIF data."""
    try:
        with Image.open(image_path) as img:
            exif = img._getexif()
            if exif:
                # Look for DateTimeOriginal (36867) or DateTime (306)
                for tag_id in [36867, 306]:
                    if tag_id in exif:
                        date_str = exif[tag_id]
                        # EXIF date format: "2023:03:14 12:30:00"
                        try:
                            return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                        except ValueError:
                            continue
    except Exception:
        pass
    return None


def get_file_modification_date(image_path: Path) -> datetime:
    """Get file modification time as fallback."""
    mtime = image_path.stat().st_mtime
    return datetime.fromtimestamp(mtime)


def get_year_from_image(image_path: Path) -> int:
    """Extract year from EXIF or file modification date."""
    exif_date = extract_exif_date(image_path)
    if exif_date:
        return exif_date.year
    
    # Fallback to file modification date
    mod_date = get_file_modification_date(image_path)
    return mod_date.year


def get_unique_destination_path(dest_dir: Path, filename: str) -> Path:
    """Get a unique destination path, handling duplicates."""
    dest_path = dest_dir / filename
    
    if not dest_path.exists():
        return dest_path
    
    # File exists, add counter
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    
    while True:
        new_filename = f"{stem}_{counter}{suffix}"
        dest_path = dest_dir / new_filename
        if not dest_path.exists():
            return dest_path
        counter += 1


def copy_photo(image_path: Path, dest_base_dir: Path, dry_run: bool = False) -> Tuple[bool, str]:
    """
    Copy a photo to the destination organized by year.
    
    Args:
        image_path: Source image path
        dest_base_dir: Base destination directory (e.g., My Pictures)
        dry_run: If True, don't actually copy
    
    Returns:
        (success, message)
    """
    try:
        # Get year from image
        year = get_year_from_image(image_path)
        
        # Create year directory
        year_dir = dest_base_dir / str(year)
        if not dry_run:
            year_dir.mkdir(parents=True, exist_ok=True)
        
        # Get destination path (handle duplicates)
        dest_path = get_unique_destination_path(year_dir, image_path.name)
        
        if dest_path.exists():
            return True, f"Skipped (already exists): {dest_path}"
        
        if dry_run:
            return True, f"Would copy to: {dest_path}"
        
        # Copy the file
        shutil.copy2(image_path, dest_path)
        return True, f"Copied to: {dest_path}"
        
    except Exception as e:
        return False, f"Error copying {image_path}: {e}"
