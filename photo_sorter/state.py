"""State module - handles pause/resume functionality."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


STATE_FILE = "state.json"
MANIFEST_FILE = "manifest.json"
BATCH_SIZE = 100


class ProcessingState:
    """Manages the processing state for pause/resume."""
    
    def __init__(self, work_dir: Path):
        self.work_dir = Path(work_dir)
        self.state_file = self.work_dir / STATE_FILE
        self.manifest_file = self.work_dir / MANIFEST_FILE
        
        # State attributes
        self.manifest_path: Optional[str] = None
        self.last_processed_index: int = 0
        self.processed_count: int = 0
        self.copied_count: int = 0
        self.skipped_count: int = 0
        self.started_at: Optional[str] = None
        self.updated_at: Optional[str] = None
    
    def exists(self) -> bool:
        """Check if a saved state exists."""
        return self.state_file.exists()
    
    def load(self) -> bool:
        """Load state from file."""
        if not self.exists():
            return False
        
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            
            self.manifest_path = data.get("manifest_file")
            self.last_processed_index = data.get("last_processed_index", 0)
            self.processed_count = data.get("processed_count", 0)
            self.copied_count = data.get("copied_count", 0)
            self.skipped_count = data.get("skipped_count", 0)
            self.started_at = data.get("started_at")
            self.updated_at = data.get("updated_at")
            
            return True
        except Exception as e:
            print(f"Error loading state: {e}")
            return False
    
    def save(self):
        """Save current state to file."""
        self.updated_at = datetime.now().isoformat()
        
        data = {
            "manifest_file": str(self.manifest_file) if self.manifest_file else None,
            "last_processed_index": self.last_processed_index,
            "processed_count": self.processed_count,
            "copied_count": self.copied_count,
            "skipped_count": self.skipped_count,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }
        
        self.work_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_manifest(self, image_paths: List[Path]):
        """Create the manifest file with all image paths."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        manifest_data = {
            "created_at": datetime.now().isoformat(),
            "total_images": len(image_paths),
            "images": [str(p) for p in image_paths],
        }
        
        with open(self.manifest_file, 'w') as f:
            json.dump(manifest_data, f, indent=2)
        
        self.manifest_path = str(self.manifest_file)
        self.started_at = datetime.now().isoformat()
        self.save()
    
    def load_manifest(self) -> List[Path]:
        """Load image paths from manifest."""
        if not self.manifest_file.exists():
            return []
        
        with open(self.manifest_file, 'r') as f:
            data = json.load(f)
        
        return [Path(p) for p in data.get("images", [])]
    
    def get_remaining_images(self) -> List[Path]:
        """Get images that haven't been processed yet."""
        all_images = self.load_manifest()
        return all_images[self.last_processed_index:]
    
    def update_progress(self, processed: int = 0, copied: int = 0, skipped: int = 0):
        """Update progress counters."""
        self.processed_count += processed
        self.copied_count += copied
        self.skipped_count += skipped
        self.last_processed_index += processed
        self.save()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics."""
        total = len(self.load_manifest())
        return {
            "total_images": total,
            "processed": self.processed_count,
            "remaining": total - self.processed_count,
            "copied": self.copied_count,
            "skipped": self.skipped_count,
            "percent_complete": (self.processed_count / total * 100) if total > 0 else 0,
        }
