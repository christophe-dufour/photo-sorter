"""CLI module - main entry point for photo sorter."""

import argparse
import random
import sys
from pathlib import Path
from typing import List, Optional

from tqdm import tqdm

from photo_sorter.scanner import scan_sources, is_screenshot_by_filename
from photo_sorter.classifier import PhotoClassifier
from photo_sorter.copier import copy_photo
from photo_sorter.state import ProcessingState, BATCH_SIZE


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


def generate_html_report(results: list, output_path: Path):
    """Generate an HTML report with clickable image paths."""
    
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
        
        html += f'    <div class="image-item real">\n'
        html += f'        <div class="filepath"><a href="{file_url}">{filepath}</a></div>\n'
        
        if "error" in d:
            html += f'        <p class="error">Error: {d["error"]}</p>\n'
        else:
            html += f'        <p class="score">Top label: <span class="label">{d["top_label"]}</span> ({d["top_score"]:.1%})</p>\n'
            html += f'        <p class="score">Real score: {d["real_score"]:.1%} | Non-real: {d["non_real_score"]:.1%}</p>\n'
        
        # Try to embed thumbnail
        html += f'        <img class="thumbnail" src="{file_url}" onerror="this.style.display=\'none\'" />\n'
        html += f'    </div>\n'
    
    html += """
    <h2>Non-Real Photos</h2>
"""
    
    for r in non_real:
        d = r["details"]
        filepath = r["path"]
        file_url = filepath.as_uri()
        
        html += f'    <div class="image-item non-real">\n'
        html += f'        <div class="filepath"><a href="{file_url}">{filepath}</a></div>\n'
        
        if "error" in d:
            html += f'        <p class="error">Error: {d["error"]}</p>\n'
        else:
            html += f'        <p class="score">Top label: <span class="label">{d["top_label"]}</span> ({d["top_score"]:.1%})</p>\n'
            html += f'        <p class="score">Real score: {d["real_score"]:.1%} | Non-real: {d["non_real_score"]:.1%}</p>\n'
        
        # Try to embed thumbnail
        html += f'        <img class="thumbnail" src="{file_url}" onerror="this.style.display=\'none\'" />\n'
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
        results.append({
            "path": img_path,
            "is_real": is_real,
            "details": details,
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
