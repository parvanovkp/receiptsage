import argparse
import sys
import os
from pathlib import Path
from typing import Optional

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from src.ocr import ReceiptOCR

def process_receipt(image_path: str, output_path: Optional[str] = None) -> None:
    """Process a single receipt image and optionally save results."""
    ocr = ReceiptOCR()
    
    print(f"\nProcessing image: {image_path}")
    try:
        results = ocr.process_image(image_path)
        
        print("\n--- OCR Results ---")
        print(f"Confidence Score: {results['confidence']:.2f}%")
        print("\nExtracted Text:")
        print("-" * 40)
        print(results['text'])
        print("-" * 40)
        
        if output_path:
            # Save results to file
            with open(output_path, 'w') as f:
                f.write(f"Confidence Score: {results['confidence']:.2f}%\n\n")
                f.write("Extracted Text:\n")
                f.write("-" * 40 + "\n")
                f.write(results['text'])
                f.write("\n" + "-" * 40)
            print(f"\nResults saved to: {output_path}")
            
    except Exception as e:
        print(f"Error processing image: {str(e)}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Test OCR on receipt images')
    parser.add_argument('image_path', help='Path to the receipt image')
    parser.add_argument('--output', '-o', help='Path to save the OCR results')
    
    args = parser.parse_args()
    
    # Validate image path
    if not os.path.exists(args.image_path):
        print(f"Error: Image file not found: {args.image_path}")
        sys.exit(1)
    
    # Process the receipt
    process_receipt(args.image_path, args.output)

if __name__ == '__main__':
    main()