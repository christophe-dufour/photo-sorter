"""Test module for classifier."""

import pytest
from pathlib import Path
from photo_sorter.classifier import PhotoClassifier, CANDIDATE_LABELS


class TestPhotoClassifier:
    """Tests for PhotoClassifier."""
    
    def test_labels_defined(self):
        """Test that candidate labels are defined."""
        assert len(CANDIDATE_LABELS) == 6
        assert "a family photo with people" in CANDIDATE_LABELS
        assert "a screenshot of a phone or computer" in CANDIDATE_LABELS
    
    def test_classifier_initialization(self):
        """Test classifier can be initialized."""
        # This will download the model on first run
        classifier = PhotoClassifier()
        assert classifier.model is not None
        assert classifier.processor is not None
    
    @pytest.mark.skip(reason="Requires actual image file")
    def test_classify_image(self, tmp_path):
        """Test classification of an image."""
        # Create a dummy test scenario
        classifier = PhotoClassifier()
        # Would need actual image to test properly
        pass
