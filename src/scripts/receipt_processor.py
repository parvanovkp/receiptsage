import os
import json
from openai import OpenAI
from pathlib import Path
from base64 import b64encode
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from dataclasses import dataclass

@dataclass
class ProcessingResult:
    """Container for processing results and errors."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None

class ReceiptProcessor:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
    
    def encode_image(self, image_path: str) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as image_file:
            return b64encode(image_file.read()).decode('utf-8')

    def transcribe(self, image_path: str) -> ProcessingResult:
        """First stage: Pure text transcription."""
        try:
            base64_image = self.encode_image(image_path)
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a receipt OCR system. Output only the exact text from the receipt, preserving all original formatting, abbreviations, and numbers. No introduction or explanation. Make sure you pay extreme attention to transcibing numbers accurately."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Transcribe this receipt exactly as shown. Preserve all text, numbers, and symbols. Output only the receipt content."},
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
                max_tokens=4096
            )
            
            transcribed_text = response.choices[0].message.content.strip()
            return ProcessingResult(success=True, data=transcribed_text)
            
        except Exception as e:
            return ProcessingResult(success=False, error=f"Transcription failed: {str(e)}")

    def normalize(self, raw_text: str) -> ProcessingResult:
        """Second stage: Structure the raw text into JSON."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a JSON conversion system. Strictly differentiate between items sold by weight and items sold by unit count."
                    },
                    {
                        "role": "user",
                        "content": f"""Convert this receipt text to JSON using these strict rules:

1. For items sold by weight (like produce, meat, fish):
   - weight: numerical amount in pounds
   - quantity: must be null
   - unit: must be "pounds"
   - unit_price: price per pound

2. For items sold by unit count (like packaged goods):
   - weight: must be null
   - quantity: number of units
   - unit: must be "each"
   - unit_price: price per item

Structure:
{{
  "metadata": {{"store": string, "address": string, "phone": string, "receipt_number": string, "date": string, "time": string}},
  "items": [{{
    "brand": string or null,
    "product": string,
    "category": string,
    "quantity": number or null,  # ONLY for unit-based items
    "weight": number or null,    # ONLY for weight-based items
    "unit": "each" or "pounds",
    "unit_price": number,
    "total_price": number,
    "is_organic": boolean,
    "savings": number or null
  }}],
  "totals": {{
    "subtotal": number,
    "total_savings": number,
    "net_sales": number,
    "bag_fee": number or null,
    "tax": [{{ "rate": number, "amount": number }}],
    "total": number
  }},
  "payment": {{ "method": string, "card_last_four": string or null, "amount": number }},
  "promotions": [{{ "description": string, "savings": number or null }}]
}}

Receipt text:
{raw_text}"""
                }
            ],
            max_tokens=4096
        )
            
            result = response.choices[0].message.content.strip()
            
            # Remove markdown if present
            if result.startswith('```') and result.endswith('```'):
                result = result.split('```')[1]
                if result.startswith('json\n'):
                    result = result[5:]
                result = result.strip()
            
            try:
                parsed_data = json.loads(result)
                return ProcessingResult(success=True, data=parsed_data)
            except json.JSONDecodeError:
                return ProcessingResult(
                    success=False,
                    error="Failed to parse JSON response",
                    raw_response=result
                )
                
        except Exception as e:
            return ProcessingResult(success=False, error=f"Normalization failed: {str(e)}")

    def process_receipt(self, image_path: str) -> ProcessingResult:
        """Process receipt through both stages."""
        transcription = self.transcribe(image_path)
        if not transcription.success:
            return transcription
        return self.normalize(transcription.data)

def print_summary(results: ProcessingResult) -> None:
    """Print receipt summary."""
    if not results.success:
        print(f"\nError: {results.error}")
        if results.raw_response:
            print("\nRaw response:", results.raw_response)
        return
        
    data = results.data
    print("\nReceipt Summary:")
    print("-" * 50)
    
    # Metadata
    metadata = data.get('metadata', {})
    print(f"Store: {metadata.get('store', 'N/A')}")
    print(f"Location: {metadata.get('address', 'N/A')}")
    print(f"Date: {metadata.get('date', 'N/A')} {metadata.get('time', '')}")
    print(f"Receipt #: {metadata.get('receipt_number', 'N/A')}")
    
    # Items
    items = data.get('items', [])
    print(f"\nItems: {len(items)}")
    print(f"Organic Items: {sum(1 for item in items if item.get('is_organic', False))}")
    
    # Categories
    categories = {}
    for item in items:
        cat = item.get('category', 'Unknown')
        categories[cat] = categories.get(cat, 0) + item.get('total_price', 0)
    
    print("\nCategory Breakdown:")
    for cat, total in sorted(categories.items()):
        print(f"{cat}: ${total:.2f}")
    
    # Totals
    totals = data.get('totals', {})
    tax_total = sum(t.get('amount', 0) for t in totals.get('tax', []))
    
    print(f"\nSubtotal: ${totals.get('subtotal', 0):.2f}")
    print(f"Savings: ${totals.get('total_savings', 0):.2f}")
    print(f"Tax: ${tax_total:.2f}")
    print(f"Total: ${totals.get('total', 0):.2f}")
    
    # Payment
    payment = data.get('payment', {})
    print(f"\nPaid with: {payment.get('method', 'N/A')} "
          f"ending in {payment.get('card_last_four', 'N/A')}")
    print("-" * 50)

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
    
    image_path = root_dir / "data" / "test_receipts" / "test1.jpg"
    if not image_path.exists():
        print(f"Error: Image file not found: {image_path}")
        return
    
    print(f"Processing receipt: {image_path}")
    processor = ReceiptProcessor(api_key)
    results = processor.process_receipt(str(image_path))
    
    output_dir = root_dir / "data" / "analyzed_receipts"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "receipt_analysis.json"
    
    with open(output_path, 'w') as f:
        if results.success:
            json.dump(results.data, f, indent=2)
        else:
            json.dump({
                "error": results.error,
                "raw_response": results.raw_response
            }, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")
    print_summary(results)

if __name__ == "__main__":
    main()