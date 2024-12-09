import os
import json
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
                        "content": "Transcribe receipt text exactly as shown. Preserve all formatting, spacing, symbols, and numbers. Focus solely on accurate text extraction."
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

class QualityCheckAgent(ReceiptAgent):
    """Agent responsible for verifying critical numerical data against original image."""
    
    def process(self, image_path: str, transcribed_text: str) -> ProcessingResult:
        start_time = time.time()
        try:
            base64_image = self.encode_image(image_path)
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """Verify these numbers ONLY against the receipt image:
- Item prices and quantities
- Subtotal, tax, total
- Receipt number, date
Reply with "VERIFIED: " + original text if correct, or corrected text if errors found.
"""
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
            
            # Handle the verified response
            if verified_text.startswith("VERIFIED: "):
                return ProcessingResult(success=True, data=transcribed_text)
            
            return ProcessingResult(success=True, data=verified_text)
            
        except Exception as e:
            return ProcessingResult(success=False, error=f"Quality check failed: {str(e)}")

class StructuredDataAgent(ReceiptAgent):
    """Combined agent for normalization and JSON formatting."""
    
    def process(self, text: str) -> ProcessingResult:
        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
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
        self.checker = QualityCheckAgent(api_key)
        self.structured_data = StructuredDataAgent(api_key)
    
    def process_receipt(self, image_path: str) -> ProcessingResult:
        """Process receipt through optimized pipeline."""
        start_time = time.time()
        try:
            # Step 1: Transcribe image
            result = self.transcriber.process(image_path)
            if not result.success:
                return result
            
            # Step 2: Quality check against original image
            checked = self.checker.process(image_path, result.data)
            if not checked.success:
                return checked
            
            # Step 3: Create structured data
            final = self.structured_data.process(checked.data)
            
            duration = time.time() - start_time
            print(f"{self.__class__.__name__} took {duration:.2f}s")
            return final
            
        except Exception as e:
            return ProcessingResult(success=False, error=f"Processing pipeline failed: {str(e)}")

def main():
    root_dir = Path(__file__).parent.parent.parent
    env_path = root_dir / '.env'
    
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        return
        
    load_dotenv(env_path)
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env file")
        return
    
    # Process single receipt image
    receipt_path = root_dir / "data" / "test_receipts" / "test1.jpg"
    if not receipt_path.exists():
        print("Error: Receipt image not found")
        return
    
    print("Processing receipt image...")
    processor = OptimizedReceiptProcessor(api_key)
    results = processor.process_receipt(str(receipt_path))
    
    output_dir = root_dir / "data" / "analyzed_receipts"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if results.success:
        # Save JSON results
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

if __name__ == "__main__":
    main()