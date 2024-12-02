import pytesseract
from PIL import Image
from typing import Dict, Any
import logging
from .image_preprocessing import ImagePreprocessor

class ReceiptOCR:
    def __init__(self):
        self.preprocessor = ImagePreprocessor()
        self._setup_logging()

    def _setup_logging(self):
        """Setup logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def process_image(self, image_path: str) -> Dict[str, Any]:
        """
        Process receipt image and extract text.
        Returns dictionary with extracted text and confidence scores.
        """
        try:
            # Preprocess image
            self.preprocessor.load_image(image_path)
            self.preprocessor.resize()
            self.preprocessor.enhance()
            
            # Extract text
            ocr_data = pytesseract.image_to_data(
                self.preprocessor.image, 
                output_type=pytesseract.Output.DICT
            )
            
            # Filter and clean results
            extracted_text = self._clean_ocr_results(ocr_data)
            
            return {
                'text': extracted_text,
                'confidence': self._calculate_confidence(ocr_data)
            }
            
        except Exception as e:
            self.logger.error(f"Error processing image {image_path}: {str(e)}")
            raise

    def _clean_ocr_results(self, ocr_data: Dict[str, Any]) -> str:
        """Clean and format OCR results."""
        # Filter out low confidence text
        confidence_threshold = 30
        text_filtered = [
            word for word, conf in zip(ocr_data['text'], ocr_data['conf'])
            if conf > confidence_threshold and str(word).strip()
        ]
        
        return ' '.join(text_filtered)

    def _calculate_confidence(self, ocr_data: Dict[str, Any]) -> float:
        """Calculate overall confidence score."""
        valid_scores = [
            score for score in ocr_data['conf']
            if score != -1  # Skip invalid confidence scores
        ]
        return sum(valid_scores) / len(valid_scores) if valid_scores else 0.0