"""Scanner module - finds all images in source directories."""

import os
from pathlib import Path
from typing import List


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.heif'}


def is_image_file(filepath: Path) -> bool:
    """Check if file is an image based on extension."""
    return filepath.suffix.lower() in IMAGE_EXTENSIONS


def is_screenshot_by_filename(filepath: Path) -> bool:
    """Pre-filter: check if filename indicates it's a screenshot."""
    name_lower = filepath.name.lower()
    screenshot_indicators = [
        'screenshot',
        'capture d\'écran',
        'capture d\'ecran',
        'capture d ecran',
        'screen recording',
        'screenrecording',
    ]
    if any(indicator in name_lower for indicator in screenshot_indicators):
        return True
    
    # Check for iOS screenshot patterns: IMG_XXXX.PNG where XXXX is a number
    # These are typically iOS screenshots
    import re
    stem = filepath.stem
    if re.match(r'^IMG_\d{3,5}$', stem, re.IGNORECASE) and filepath.suffix.lower() == '.png':
        return True
    
    # Check for "Untitled" PNG files - often screenshots saved from browsers/apps
    if stem.lower().startswith('untitled') and filepath.suffix.lower() == '.png':
        return True
    
    return False


def scan_directory(directory: Path) -> List[Path]:
    """Recursively scan directory for all image files."""
    images = []
    
    for root, dirs, files in os.walk(directory):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for filename in files:
            filepath = Path(root) / filename
            if is_image_file(filepath):
                images.append(filepath)
    
    return images


def scan_sources(source_dirs: List[Path]) -> List[Path]:
    """Scan all source directories and return unique image paths."""
    all_images = []
    seen_paths = set()
    
    for source_dir in source_dirs:
        if not source_dir.exists():
            print(f"Warning: Source directory does not exist: {source_dir}")
            continue
            
        images = scan_directory(source_dir)
        for img_path in images:
            # Use resolved path to avoid duplicates
            resolved = img_path.resolve()
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                all_images.append(img_path)
    
    return all_images
