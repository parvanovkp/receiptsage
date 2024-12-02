from PIL import Image
import numpy as np

class ImagePreprocessor:
    def __init__(self):
        self.image = None

    def load_image(self, image_path: str) -> None:
        """Load image from path."""
        try:
            self.image = Image.open(image_path)
        except Exception as e:
            raise ValueError(f"Failed to load image: {str(e)}")

    def resize(self, max_dimension: int = 1800) -> None:
        """Resize image while maintaining aspect ratio."""
        if self.image is None:
            raise ValueError("No image loaded")
        
        # Fix: Calculate ratio correctly
        width, height = self.image.size
        ratio = min(max_dimension / width, max_dimension / height)
        new_size = (int(width * ratio), int(height * ratio))
        self.image = self.image.resize(new_size, Image.Resampling.LANCZOS)

    def enhance(self) -> None:
        """Enhance image for better OCR results."""
        if self.image is None:
            raise ValueError("No image loaded")
        
        # Convert to grayscale
        self.image = self.image.convert('L')
        
        # Increase contrast
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(self.image)
        self.image = enhancer.enhance(3.0)