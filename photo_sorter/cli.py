"""CLI module - main entry point for photo sorter."""

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from tqdm import tqdm

from photo_sorter.scanner import scan_sources, is_screenshot_by_filename
from photo_sorter.classifier import PhotoClassifier
from photo_sorter.copier import copy_photo
from photo_sorter.state import ProcessingState, BATCH_SIZE


def extract_metadata(image_path: Path) -> Dict[str, Any]:
    """Extract EXIF metadata from image."""
    metadata = {
        "has_exif": False,
        "date_taken": None,
        "camera_make": None,
        "camera_model": None,
        "gps": None,
        "dimensions": None,
        "file_size_kb": None,
    }
    
    try:
        # Get file size
        metadata["file_size_kb"] = round(image_path.stat().st_size / 1024, 2)
        
        with Image.open(image_path) as img:
            metadata["dimensions"] = f"{img.size[0]}x{img.size[1]}"
            metadata["format"] = img.format
            
            exif = img._getexif()
            if exif:
                metadata["has_exif"] = True
                
                # Extract date taken
                for tag_id in [36867, 306]:  # DateTimeOriginal, DateTime
                    if tag_id in exif:
                        date_str = exif[tag_id]
                        try:
                            dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                            metadata["date_taken"] = dt.isoformat()
                            break
                        except ValueError:
                            pass
                
                # Extract camera info
                for tag_id, tag_name in TAGS.items():
                    if tag_id in exif:
                        if tag_name == "Make":
                            metadata["camera_make"] = str(exif[tag_id]).strip()
                        elif tag_name == "Model":
                            metadata["camera_model"] = str(exif[tag_id]).strip()
                
                # Extract GPS info
                if 34853 in exif:  # GPSInfo tag
                    gps_info = {}
                    gps_data = exif[34853]
                    for key in gps_data.keys():
                        decode = GPSTAGS.get(key, key)
                        gps_info[decode] = gps_data[key]
                    
                    # Convert to readable format
                    if gps_info:
                        metadata["gps"] = gps_info
    
    except Exception as e:
        metadata["error"] = str(e)
    
    return metadata


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="AI-powered photo sorting tool using CLIP classification"
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="Source directory (can be specified multiple times)",
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Destination base directory (e.g., 'My Pictures')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without copying files",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous run",
    )
    parser.add_argument(
        "--work-dir",
        default=".",
        help="Working directory for state and manifest files (default: current directory)",
    )
    parser.add_argument(
        "--calibrate",
        type=int,
        metavar="N",
        help="Test on N random images to calibrate classifier",
    )
    return parser.parse_args()


def format_metadata(metadata: Dict[str, Any]) -> str:
    """Format metadata as HTML."""
    if not metadata or metadata.get("error"):
        return '<p class="metadata-error">No metadata available</p>'
    
    html_parts = ['<div class="metadata">']
    html_parts.append('<h4>📊 Metadata</h4>')
    html_parts.append('<table class="metadata-table">')
    
    # File info
    html_parts.append('<tr><td class="meta-label">Format:</td>')
    html_parts.append(f'<td>{metadata.get("format", "Unknown")}</td></tr>')
    
    html_parts.append('<tr><td class="meta-label">Dimensions:</td>')
    html_parts.append(f'<td>{metadata.get("dimensions", "Unknown")}</td></tr>')
    
    html_parts.append('<tr><td class="meta-label">File Size:</td>')
    size_kb = metadata.get("file_size_kb")
    if size_kb:
        html_parts.append(f'<td>{size_kb:.1f} KB</td></tr>')
    else:
        html_parts.append('<td>Unknown</td></tr>')
    
    # EXIF data
    if metadata.get("has_exif"):
        html_parts.append('<tr class="exif-section"><td colspan="2"><strong>EXIF Data:</strong></td></tr>')
        
        if metadata.get("date_taken"):
            html_parts.append('<tr><td class="meta-label">Date Taken:</td>')
            html_parts.append(f'<td>{metadata["date_taken"]}</td></tr>')
        
        if metadata.get("camera_make") or metadata.get("camera_model"):
            camera = " ".join(filter(None, [metadata.get("camera_make"), metadata.get("camera_model")]))
            html_parts.append('<tr><td class="meta-label">Camera:</td>')
            html_parts.append(f'<td>{camera}</td></tr>')
        
        if metadata.get("gps"):
            html_parts.append('<tr><td class="meta-label">GPS:</td>')
            html_parts.append(f'<td>✓ Present</td></tr>')
    else:
        html_parts.append('<tr><td colspan="2" class="no-exif">❌ No EXIF data</td></tr>')
    
    html_parts.append('</table>')
    html_parts.append('</div>')
    
    return '\n'.join(html_parts)


def create_thumbnail_for_report(image_path: Path, report_dir: Path, max_size: int = 300) -> str:
    """Create a thumbnail for the report. For HEIC/HEIF, convert to JPEG."""
    try:
        from PIL import Image
        
        # Check if it's a HEIC/HEIF file that needs conversion
        ext = image_path.suffix.lower()
        if ext in ['.heic', '.heif']:
            # Create a JPEG thumbnail
            thumb_filename = f"thumb_{image_path.stem}.jpg"
            thumb_path = report_dir / thumb_filename
            
            if not thumb_path.exists():
                with Image.open(image_path) as img:
                    img.thumbnail((max_size, max_size))
                    # Convert to RGB for JPEG
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    img.save(thumb_path, 'JPEG', quality=85)
            
            return thumb_path.as_uri()
        else:
            # For other formats, just return the file URI
            return image_path.as_uri()
    except Exception as e:
        # If conversion fails, return the original URI
        return image_path.as_uri()


def generate_html_report(results: list, output_path: Path):
    """Generate an HTML report with clickable image paths and metadata."""
    
    # Create a directory for thumbnails
    thumbs_dir = output_path.parent / f"{output_path.stem}_thumbnails"
    thumbs_dir.mkdir(exist_ok=True)
    
    real_photos = [r for r in results if r["is_real"]]
    non_real = [r for r in results if not r["is_real"]]
    
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Photo Sorter Calibration Report</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }
        h1 { color: #333; }
        h2 { color: #555; margin-top: 30px; }
        h4 { margin: 10px 0 5px 0; color: #666; }
        .summary { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .image-item { background: white; padding: 15px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .real { border-left: 4px solid #4CAF50; }
        .non-real { border-left: 4px solid #f44336; }
        .error { border-left: 4px solid #ff9800; }
        .filepath { font-family: monospace; background: #f0f0f0; padding: 5px 10px; border-radius: 4px; display: inline-block; margin: 5px 0; }
        .filepath a { color: #2196F3; text-decoration: none; }
        .filepath a:hover { text-decoration: underline; }
        .score { color: #666; font-size: 14px; }
        .label { font-weight: bold; }
        .real-label { color: #4CAF50; }
        .non-real-label { color: #f44336; }
        img.thumbnail { max-width: 200px; max-height: 200px; border-radius: 4px; margin-top: 10px; }
        .metadata { margin-top: 10px; padding: 10px; background: #f9f9f9; border-radius: 4px; }
        .metadata-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .metadata-table td { padding: 3px 8px; }
        .meta-label { color: #666; font-weight: bold; width: 120px; }
        .exif-section { background: #e3f2fd; }
        .no-exif { color: #999; font-style: italic; }
        .metadata-error { color: #f44336; }
        .content-wrapper { display: flex; gap: 20px; align-items: flex-start; }
        .image-section { flex: 0 0 auto; }
        .info-section { flex: 1; }
    </style>
</head>
<body>
    <h1>Photo Sorter Calibration Report</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Total images tested:</strong> """ + str(len(results)) + """</p>
        <p><strong class="real-label">Real photos detected:</strong> """ + str(len(real_photos)) + """</p>
        <p><strong class="non-real-label">Non-real photos detected:</strong> """ + str(len(non_real)) + """</p>
    </div>
    
    <h2>Real Photos</h2>
"""
    
    for r in real_photos:
        d = r["details"]
        filepath = r["path"]
        file_url = filepath.as_uri()
        thumb_url = create_thumbnail_for_report(filepath, thumbs_dir)
        metadata = r.get("metadata", {})
        
        html += f'    <div class="image-item real">\n'
        html += f'        <div class="content-wrapper">\n'
        html += f'            <div class="image-section">\n'
        html += f'                <img class="thumbnail" src="{thumb_url}" onerror="this.style.display=\'none\'" />\n'
        html += f'            </div>\n'
        html += f'            <div class="info-section">\n'
        html += f'                <div class="filepath"><a href="{file_url}">{filepath}</a></div>\n'
        
        if "error" in d:
            html += f'                <p class="error">Error: {d["error"]}</p>\n'
        else:
            html += f'                <p class="score">Top label: <span class="label">{d["top_label"]}</span> ({d["top_score"]:.1%})</p>\n'
            html += f'                <p class="score">Real score: {d["real_score"]:.1%} | Non-real: {d["non_real_score"]:.1%}</p>\n'
        
        # Add metadata
        html += format_metadata(metadata)
        
        html += f'            </div>\n'
        html += f'        </div>\n'
        html += f'    </div>\n'
    
    html += """
    <h2>Non-Real Photos</h2>
"""
    
    for r in non_real:
        d = r["details"]
        filepath = r["path"]
        file_url = filepath.as_uri()
        metadata = r.get("metadata", {})
        
        html += f'    <div class="image-item non-real">\n'
        html += f'        <div class="content-wrapper">\n'
        html += f'            <div class="image-section">\n'
        html += f'                <img class="thumbnail" src="{file_url}" onerror="this.style.display=\'none\'" />\n'
        html += f'            </div>\n'
        html += f'            <div class="info-section">\n'
        html += f'                <div class="filepath"><a href="{file_url}">{filepath}</a></div>\n'
        
        if "error" in d:
            html += f'                <p class="error">Error: {d["error"]}</p>\n'
        else:
            html += f'                <p class="score">Top label: <span class="label">{d["top_label"]}</span> ({d["top_score"]:.1%})</p>\n'
            html += f'                <p class="score">Real score: {d["real_score"]:.1%} | Non-real: {d["non_real_score"]:.1%}</p>\n'
        
        # Add metadata
        html += format_metadata(metadata)
        
        html += f'            </div>\n'
        html += f'        </div>\n'
        html += f'    </div>\n'
    
    html += """
</body>
</html>
"""
    
    output_path.write_text(html, encoding='utf-8')
    return output_path


def calibrate_classifier(image_paths: List[Path], num_samples: int = 30, output_report: Optional[Path] = None):
    """Test classifier on random samples to calibrate."""
    print(f"\n{'='*60}")
    print(f"CALIBRATION MODE: Testing on {num_samples} random images")
    print(f"{'='*60}\n")
    
    if len(image_paths) < num_samples:
        print(f"Warning: Only {len(image_paths)} images available, using all")
        samples = image_paths
    else:
        samples = random.sample(image_paths, num_samples)
    
    classifier = PhotoClassifier()
    
    results = []
    for img_path in tqdm(samples, desc="Classifying"):
        is_real, details = classifier.classify(img_path)
        metadata = extract_metadata(img_path)
        results.append({
            "path": img_path,
            "is_real": is_real,
            "details": details,
            "metadata": metadata,
        })
    
    # Print results
    print("\n" + "="*60)
    print("CALIBRATION RESULTS")
    print("="*60)
    
    real_photos = [r for r in results if r["is_real"]]
    non_real = [r for r in results if not r["is_real"]]
    
    print(f"\nReal photos detected: {len(real_photos)}/{num_samples}")
    print(f"Non-real photos detected: {len(non_real)}/{num_samples}")
    
    print("\n--- Real Photos ---")
    for r in real_photos[:5]:
        d = r["details"]
        print(f"  ✓ {r['path'].name}")
        if "error" in d:
            print(f"    Error: {d['error']}")
        else:
            print(f"    Top label: {d['top_label']} ({d['top_score']:.2%})")
            print(f"    Real score: {d['real_score']:.2%}, Non-real: {d['non_real_score']:.2%}")
    
    print("\n--- Non-Real Photos ---")
    for r in non_real[:5]:
        d = r["details"]
        print(f"  ✗ {r['path'].name}")
        if "error" in d:
            print(f"    Error: {d['error']}")
        else:
            print(f"    Top label: {d['top_label']} ({d['top_score']:.2%})")
            print(f"    Real score: {d['real_score']:.2%}, Non-real: {d['non_real_score']:.2%}")
    
    if len(real_photos) + len(non_real) < num_samples:
        errors = num_samples - len(real_photos) - len(non_real)
        print(f"\n⚠ {errors} images failed to process")
    
    # Generate HTML report
    if output_report is None:
        output_report = Path.cwd() / "calibration_report.html"
    
    report_path = generate_html_report(results, output_report)
    print(f"\n📄 Full report saved to: {report_path}")
    print(f"   Open this file in your browser to view all images with clickable links")
    
    print("\n" + "="*60)
    print("Review the results above. If accuracy looks good, proceed with full run.")
    print("="*60 + "\n")


def process_images(image_paths: List[Path], dest_dir: Path, state: ProcessingState, 
                   dry_run: bool = False, classifier: Optional[PhotoClassifier] = None):
    """Process a batch of images."""
    if classifier is None:
        classifier = PhotoClassifier()
    
    copied = 0
    skipped = 0
    errors = 0
    
    for img_path in tqdm(image_paths, desc="Processing", leave=False):
        try:
            # Pre-filter screenshots
            if is_screenshot_by_filename(img_path):
                skipped += 1
                continue
            
            # Classify
            is_real, details = classifier.classify(img_path)
            
            if not is_real:
                skipped += 1
                continue
            
            # Copy real photo
            success, message = copy_photo(img_path, dest_dir, dry_run)
            
            if success:
                if "Copied" in message or "Would copy" in message:
                    copied += 1
                else:
                    skipped += 1
            else:
                errors += 1
                print(f"Error: {message}")
        
        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Saving state...")
            state.update_progress(processed=image_paths.index(img_path), copied=copied, skipped=skipped)
            sys.exit(0)
        except Exception as e:
            print(f"Error processing {img_path}: {e}")
            errors += 1
    
    state.update_progress(processed=len(image_paths), copied=copied, skipped=skipped)
    return copied, skipped, errors


def main():
    """Main entry point."""
    args = parse_args()
    
    # Convert to Path objects
    source_dirs = [Path(s).expanduser().resolve() for s in args.source]
    dest_dir = Path(args.dest).expanduser().resolve()
    work_dir = Path(args.work_dir).expanduser().resolve()
    
    # Initialize state
    state = ProcessingState(work_dir)
    
    # Resume or start fresh
    if args.resume and state.exists():
        print("Resuming from previous run...")
        state.load()
        stats = state.get_stats()
        print(f"Progress: {stats['processed']}/{stats['total_images']} images ({stats['percent_complete']:.1f}%)")
        image_paths = state.get_remaining_images()
    else:
        # Scan sources
        print("Scanning source directories...")
        image_paths = scan_sources(source_dirs)
        print(f"Found {len(image_paths)} unique images")
        
        if len(image_paths) == 0:
            print("No images found. Exiting.")
            return
        
        # Create manifest
        state.create_manifest(image_paths)
        
        # Calibration mode
        if args.calibrate:
            calibrate_classifier(image_paths, args.calibrate)
            return
    
    print(f"\nDestination: {dest_dir}")
    print(f"Dry run: {args.dry_run}")
    print(f"Total images to process: {len(image_paths)}")
    print(f"Estimated time: ~{len(image_paths) * 2.5 / 3600:.1f} hours\n")
    
    if not args.dry_run:
        confirm = input("Proceed with copy? (yes/no): ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return
    
    # Initialize classifier
    classifier = PhotoClassifier()
    
    # Process in batches
    for i in range(0, len(image_paths), BATCH_SIZE):
        batch = image_paths[i:i + BATCH_SIZE]
        copied, skipped, errors = process_images(
            batch, dest_dir, state, args.dry_run, classifier
        )
        
        stats = state.get_stats()
        print(f"Batch complete: {copied} copied, {skipped} skipped, {errors} errors")
        print(f"Progress: {stats['processed']}/{stats['total_images']} ({stats['percent_complete']:.1f}%)\n")
    
    print("="*60)
    print("Processing complete!")
    stats = state.get_stats()
    print(f"Total processed: {stats['processed']}")
    print(f"Copied: {stats['copied']}")
    print(f"Skipped: {stats['skipped']}")
    print("="*60)


if __name__ == "__main__":
    main()
