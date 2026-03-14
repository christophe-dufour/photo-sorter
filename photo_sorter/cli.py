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


def calibrate_classifier(image_paths: List[Path], num_samples: int = 30):
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
        print(f"    Top label: {d['top_label']} ({d['top_score']:.2%})")
        print(f"    Real score: {d['real_score']:.2%}, Non-real: {d['non_real_score']:.2%}")
    
    print("\n--- Non-Real Photos ---")
    for r in non_real[:5]:
        d = r["details"]
        print(f"  ✗ {r['path'].name}")
        print(f"    Top label: {d['top_label']} ({d['top_score']:.2%})")
        print(f"    Real score: {d['real_score']:.2%}, Non-real: {d['non_real_score']:.2%}")
    
    if len(real_photos) + len(non_real) < num_samples:
        errors = num_samples - len(real_photos) - len(non_real)
        print(f"\n⚠ {errors} images failed to process")
    
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
