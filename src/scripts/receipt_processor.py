import os
import json
import argparse
from openai import OpenAI
from pathlib import Path
from base64 import b64encode
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from dataclasses import dataclass
import time

@dataclass
class ProcessingResult:
    """Container for processing results and errors."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None

class ReceiptAgent:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
    
    def encode_image(self, image_path: str) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as image_file:
            return b64encode(image_file.read()).decode('utf-8')

class TranscriptionAgent(ReceiptAgent):
    """Agent responsible for transcribing text from receipt images."""
    
    def process(self, image_path: str) -> ProcessingResult:
        start_time = time.time()
        try:
            base64_image = self.encode_image(image_path)
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "Transcribe receipt text exactly as shown. Preserve all formatting, spacing, symbols, and numbers. Focus solely on accurate text extraction. Pay special attention to product names, brands and prices."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract text from this receipt image"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2048
            )
            
            duration = time.time() - start_time
            print(f"{self.__class__.__name__} took {duration:.2f}s")
            return ProcessingResult(success=True, data=response.choices[0].message.content.strip())
            
        except Exception as e:
            return ProcessingResult(success=False, error=f"Transcription failed: {str(e)}")

class TextMergingAgent(ReceiptAgent):
    """Agent responsible for reconstructing complete receipt text from multiple overlapping transcriptions."""
    
    def process(self, transcriptions: List[str]) -> ProcessingResult:
        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a receipt reconstruction specialist. Your task is to:
1. Analyze multiple transcriptions of the same receipt that may be partial or overlapping
2. Reconstruct a single, complete receipt text as if it was transcribed from one perfect image
3. Handle conflicts and ambiguities by:
   - Using the clearest/most complete version of each item description
   - Choosing the most consistent price when variations exist
   - Ensuring all unique items are preserved
   - Maintaining correct receipt structure (header → items → totals → footer)
4. Remove any duplicated information
5. Ensure numerical consistency (e.g., item prices add up to subtotal)
6. Preserve original formatting and layout

Output just the reconstructed receipt text with no explanations or annotations."""
                    },
                    {
                        "role": "user",
                        "content": "Reconstruct a complete receipt from these overlapping transcriptions:\n\n" + 
                                 "\n=====NEXT TRANSCRIPTION=====\n".join(transcriptions)
                    }
                ],
                max_tokens=2048
            )
            
            duration = time.time() - start_time
            print(f"{self.__class__.__name__} took {duration:.2f}s")
            return ProcessingResult(success=True, data=response.choices[0].message.content.strip())
            
        except Exception as e:
            return ProcessingResult(success=False, error=f"Text merging failed: {str(e)}")

class QualityCheckAgent(ReceiptAgent):
    """Agent responsible for verifying critical numerical data against original image."""
    
    def process(self, image_path: str, transcribed_text: str) -> ProcessingResult:
        start_time = time.time()
        try:
            base64_image = self.encode_image(image_path)
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """Verify these numbers ONLY against the receipt image:
- Item prices and quantities
- Subtotal, tax, total
- Receipt number, date
Reply with "VERIFIED: " + original text if correct, or corrected text if errors found."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Verify numerical data in this text against the receipt image:\n\n{transcribed_text}"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2048
            )
            
            verified_text = response.choices[0].message.content.strip()
            duration = time.time() - start_time
            print(f"{self.__class__.__name__} took {duration:.2f}s")
            
            if verified_text.startswith("VERIFIED: "):
                return ProcessingResult(success=True, data=transcribed_text)
            
            return ProcessingResult(success=True, data=verified_text)
            
        except Exception as e:
            return ProcessingResult(success=False, error=f"Quality check failed: {str(e)}")

class StructuredDataAgent(ReceiptAgent):
    """Agent for normalization and JSON formatting."""
    
    def process(self, text: str) -> ProcessingResult:
        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """Convert receipt text to valid JSON, ensuring:
1. All monetary values must be numbers (not strings)
2. All quantities and weights must be numbers (not strings)
3. All rates must be numbers (not strings)
4. Date and time should be strings in specified format
5. Expand all abbreviations to full English words

Required structure:
{
  "metadata": {
    "store": string,
    "address": string,
    "phone": string,
    "receipt_number": string,
    "date": "MM/DD/YYYY",
    "time": "HH:MM AM/PM"
  },
  "items": [{
    "brand": string or null,
    "product": string,
    "category": string,
    "quantity": number or null,
    "weight": number or null,
    "unit": "pounds" or "each",
    "unit_price": number,
    "total_price": number,
    "is_organic": boolean,
    "savings": number or null
  }],
  "totals": {
    "subtotal": number,
    "total_savings": number,
    "net_sales": number,
    "bag_fee": number or null,
    "tax": [{"rate": number, "amount": number}],
    "total": number
  },
  "payment": {
    "method": string,
    "card_last_four": string or null,
    "amount": number
  },
  "promotions": [{
    "description": string,
    "savings": number
  }]
}"""
                    },
                    {
                        "role": "user",
                        "content": f"Convert this receipt text to structured JSON with proper data types:\n\n{text}"
                    }
                ],
                max_tokens=2048
            )
            
            result = response.choices[0].message.content.strip()
            
            # Clean up any markdown formatting
            if result.startswith('```') and result.endswith('```'):
                result = result.split('```')[1]
                if result.startswith('json\n'):
                    result = result[5:]
                result = result.strip()
            
            try:
                parsed_data = json.loads(result)
                
                # Verify critical data types
                if not isinstance(parsed_data.get('totals', {}).get('subtotal'), (int, float)):
                    raise ValueError("Subtotal must be a number")
                if not isinstance(parsed_data.get('totals', {}).get('total'), (int, float)):
                    raise ValueError("Total must be a number")
                
                duration = time.time() - start_time
                print(f"{self.__class__.__name__} took {duration:.2f}s")
                return ProcessingResult(success=True, data=parsed_data)
            except json.JSONDecodeError:
                return ProcessingResult(
                    success=False, 
                    error="Failed to parse JSON response",
                    raw_response=result
                )
                
        except Exception as e:
            return ProcessingResult(success=False, error=f"Structured data formatting failed: {str(e)}")

class OptimizedReceiptProcessor:
    """Optimized receipt processing system."""
    
    def __init__(self, api_key: str):
        self.transcriber = TranscriptionAgent(api_key)
        self.merger = TextMergingAgent(api_key)
        self.checker = QualityCheckAgent(api_key)
        self.structured_data = StructuredDataAgent(api_key)
    
    def process_receipt_folder(self, folder_path: Path) -> ProcessingResult:
        """Process all receipt images in a folder."""
        start_time = time.time()
        try:
            # Get all jpg images in the folder
            image_paths = list(folder_path.glob('*.jpg'))
            if not image_paths:
                return ProcessingResult(success=False, error="No receipt images found in folder")

            print(f"Found {len(image_paths)} receipt images")
            
            # Step 1: Transcribe all images
            transcriptions = []
            for image_path in image_paths:
                print(f"Transcribing {image_path.name}...")
                result = self.transcriber.process(str(image_path))
                if result.success:
                    transcriptions.append(result.data)
                else:
                    print(f"Warning: Failed to transcribe {image_path.name}: {result.error}")
            
            if not transcriptions:
                return ProcessingResult(success=False, error="No successful transcriptions")
            
            # Step 2: Merge transcriptions if multiple images exist
            if len(transcriptions) > 1:
                print("Merging multiple transcriptions...")
                merged = self.merger.process(transcriptions)
                if not merged.success:
                    return merged
                text_for_checking = merged.data
            else:
                text_for_checking = transcriptions[0]
            
            # Step 3: Quality check against the most complete image
            print("Performing quality check...")
            checked = self.checker.process(str(image_paths[0]), text_for_checking)
            if not checked.success:
                return checked
            
            # Step 4: Create structured data
            print("Creating structured data...")
            final = self.structured_data.process(checked.data)
            
            duration = time.time() - start_time
            print(f"{self.__class__.__name__} took {duration:.2f}s")
            return final
            
        except Exception as e:
            return ProcessingResult(success=False, error=f"Processing pipeline failed: {str(e)}")

def process_receipt(receipt_folder: str, api_key: str) -> None:
    """Process a receipt folder and save results."""
    folder_path = Path(receipt_folder)
    if not folder_path.exists():
        print(f"Error: Folder not found: {folder_path}")
        return
        
    print(f"\nProcessing receipt folder: {folder_path}")
    processor = OptimizedReceiptProcessor(api_key)
    results = processor.process_receipt_folder(folder_path)
    
    # Create analysis subfolder
    output_dir = folder_path / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if results.success:
        # Save results
        json_path = output_dir / "receipt_analysis.json"
        with open(json_path, 'w') as f:
            json.dump(results.data, f, indent=2)
        print(f"\nResults saved to: {json_path}")
        
        # Print summary
        print("\nProcessed Receipt Summary:")
        print("-" * 50)
        if "metadata" in results.data:
            meta = results.data["metadata"]
            print(f"Store: {meta.get('store', 'N/A')}")
            print(f"Date: {meta.get('date', 'N/A')} {meta.get('time', '')}")
            print(f"Receipt #: {meta.get('receipt_number', 'N/A')}")
        if "items" in results.data:
            print(f"\nTotal Items: {len(results.data['items'])}")
        if "totals" in results.data:
            totals = results.data["totals"]
            print(f"Subtotal: ${totals.get('subtotal', 0):.2f}")
            print(f"Total: ${totals.get('total', 0):.2f}")
    else:
        print(f"\nError: {results.error}")
        if results.raw_response:
            print(f"\nRaw response: {results.raw_response}")

def main():
    parser = argparse.ArgumentParser(description='Process receipt images in a folder')
    parser.add_argument('receipt_folder', help='Path to the folder containing receipt images')
    parser.add_argument('--env', help='Path to .env file', default='.env')
    
    args = parser.parse_args()
    
    # Load environment variables
    env_path = Path(args.env)
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        return
        
    load_dotenv(env_path)
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env file")
        return
    
    process_receipt(args.receipt_folder, api_key)

if __name__ == "__main__":
    main()