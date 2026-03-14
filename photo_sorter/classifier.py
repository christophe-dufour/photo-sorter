"""Classifier module - uses CLIP to identify real photos."""

from pathlib import Path
from typing import List, Tuple

from PIL import Image
from pillow_heif import register_heif_opener
from transformers import CLIPProcessor, CLIPModel
import torch

# Register HEIF/HEIC support
register_heif_opener()


# Labels for zero-shot classification
CANDIDATE_LABELS = [
    # Real photos
    "a family photo with people",
    "a landscape or nature photo",
    "a photo of food or objects",
    # Not real photos - screenshots and digital content
    "a screenshot of a phone or computer screen",
    "a screenshot with status bar showing time and battery",
    "a screenshot from a mobile app with user interface",
    "a photo of a document or paper",
    "a photo of a receipt or bill",
]

REAL_PHOTO_LABELS = [
    "a family photo with people",
    "a landscape or nature photo",
    "a photo of food or objects",
]

NON_REAL_LABELS = [
    "a screenshot of a phone or computer screen",
    "a screenshot with status bar showing time and battery",
    "a screenshot from a mobile app with user interface",
    "a photo of a document or paper",
    "a photo of a receipt or bill",
]


class PhotoClassifier:
    """CLIP-based photo classifier."""
    
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        """Initialize CLIP model and processor."""
        print(f"Loading CLIP model: {model_name}")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_name)
        print(f"Model loaded on {self.device}")
    
    def classify(self, image_path: Path) -> Tuple[bool, dict]:
        """
        Classify an image as real photo or not.
        
        Returns:
            (is_real_photo, details_dict)
        """
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as e:
            return False, {"error": f"Failed to open image: {e}"}
        
        # Process image and text
        inputs = self.processor(
            text=CANDIDATE_LABELS,
            images=image,
            return_tensors="pt",
            padding=True
        ).to(self.device)
        
        # Get predictions
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits_per_image = outputs.logits_per_image
            probs = logits_per_image.softmax(dim=1)
        
        # Convert to percentages
        probs = probs.cpu().numpy()[0]
        
        # Build results dict
        results = {
            label: float(prob)
            for label, prob in zip(CANDIDATE_LABELS, probs)
        }
        
        # Calculate real vs non-real scores
        real_score = sum(results[label] for label in REAL_PHOTO_LABELS)
        non_real_score = sum(results[label] for label in NON_REAL_LABELS)
        
        is_real = real_score > non_real_score
        
        return is_real, {
            "is_real_photo": is_real,
            "real_score": real_score,
            "non_real_score": non_real_score,
            "all_scores": results,
            "top_label": max(results, key=lambda k: results[k]),
            "top_score": max(results.values()),
        }
