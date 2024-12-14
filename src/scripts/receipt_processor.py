import os
import json
import argparse
from openai import OpenAI
from pathlib import Path
from base64 import b64encode
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from dataclasses import dataclass

@dataclass
class ProcessingResult:
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None

class ReceiptProcessor:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        
    def encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return b64encode(image_file.read()).decode('utf-8')

    def transcribe_images(self, image_paths: List[str]) -> ProcessingResult:
        """Transcribe multiple receipt images and merge them."""
        try:
            # Handle single image case directly
            if len(image_paths) == 1:
                return self.process_receipt(image_paths[0])

            print("Processing multiple receipt images...")
            
            # Gather all transcriptions
            all_texts = []
            for img_path in image_paths:
                print(f"Processing: {Path(img_path).name}")
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    temperature=0.01,
                    messages=[
                        {
                            "role": "system",
                            "content": """Transcribe this receipt segment exactly as shown, preserving:
1. All text, numbers, and formatting exactly as they appear
2. Item descriptions, quantities, and prices
3. Any visible header or footer information
4. Any partial lines or items

Look carefully for:
- Items that span multiple lines
- All price information
- Savings and discounts
- Every single item on the receipt
Output raw text only."""
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Transcribe this receipt segment:"},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{self.encode_image(img_path)}",
                                        "detail": "high"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=1024
                )
                all_texts.append(response.choices[0].message.content.strip())

            # Merge transcriptions
            print("Merging overlapping segments...")
            response = self.client.chat.completions.create(
                model="gpt-4o",
                temperature=0.01,
                messages=[
                    {
                        "role": "system",
                        "content": """Merge these overlapping receipt segments into a single coherent receipt.
Rules:
1. Handle overlapping sections by keeping the clearest/most complete version
2. Maintain the correct order of items
3. Ensure no duplicate items
4. Preserve all price information exactly
5. Keep all header and footer information
Output the complete merged receipt text."""
                    },
                    {
                        "role": "user",
                        "content": "Merge these receipt segments:\n\n" + 
                                 "\n---NEXT SEGMENT---\n".join(all_texts)
                    }
                ],
                max_tokens=2048
            )
            
            merged_text = response.choices[0].message.content.strip()
            
            # Process merged text into structured format
            return self.extract_structured_data(merged_text)
            
        except Exception as e:
            return ProcessingResult(success=False, error=f"Failed to process multiple images: {str(e)}")

    def process_receipt(self, image_path: str) -> ProcessingResult:
        """Process a single receipt image."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                temperature=0.01,
                messages=[
                    {
                        "role": "system",
                        "content": """Extract receipt data into JSON following this exact schema:
{
  "metadata": {
    "store": string,
    "address": string,
    "phone": string | null,
    "receipt_number": string,
    "date": string,
    "time": string
  },
  "items": [{
    "brand": string | null,     // Full brand name, not abbreviated
    "product": string,          // Full product name, not abbreviated
    "product_type": string,     // Generic product type (e.g., toilet paper, pie, bread, salmon)
    "category": string,         // One of: Produce, Bakery, Household, Meat, Seafood, Grocery, Miscellaneous
    "quantity": number | null,  // Use for unit items
    "weight": number | null,    // Use for weighted items (in pounds)
    "unit": "pounds" | "each",
    "unit_price": number,
    "total_price": number,
    "is_organic": boolean,
    "savings": number | null
  }],
  "totals": {
    "subtotal": number,
    "total_savings": number,
    "tax": [{
      "rate": number,
      "amount": number
    }],
    "total": number
  },
  "payment": {
    "method": string,
    "card_last_four": string | null,
    "amount": number
  }
}

Rules:
1. Never use abbreviations in product or brand names. Examples:
   - "FCL TSSUE" → "Facial Tissue"
   - "SDROGH" → "Sourdough"
   - "RSTD" → "Roasted"
   - "PEELD" → "Peeled"
   - "GRLC" → "Garlic"
   - "HD" → "Heavy Duty"
   - "OG" → "Organic"
   - "AK" → "Alaskan"
   - "SOCKEY" → "Sockeye"
   - "FLLT" → "Fillet"

2. For product_type, use generic product categories like:
   - facial tissue
   - toilet paper
   - aluminum foil
   - sourdough bread
   - apple pie
   - asparagus
   - garlic
   - bananas
   - hummus
   - turkey
   - salmon

3. Brand name normalization:
   - "365WFM" → "365 Whole Foods Market"
   - "BMBMBO" → "Bamboo"
   - "SWFM" → "Whole Foods Market"

4. Important:
   - Check for and include every item on the receipt
   - Look carefully for items that might span multiple lines
   - For weighted items: use weight in pounds, set quantity null
   - For unit items: use quantity, set weight null
   - Keep any certification or grade indicators (MSC, S3) in the product name"""
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract complete receipt data with full product names:"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{self.encode_image(image_path)}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096,
                response_format={ "type": "json_object" }
            )
            
            data = json.loads(response.choices[0].message.content)
            return ProcessingResult(success=True, data=data)
            
        except Exception as e:
            return ProcessingResult(success=False, error=str(e))

    def extract_structured_data(self, text: str) -> ProcessingResult:
        """Convert merged text to structured JSON."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                temperature=0.01,
                messages=[
                    {
                        "role": "system",
                        "content": """Extract receipt data into JSON following this exact schema:
{
  "metadata": {
    "store": string,
    "address": string,
    "phone": string | null,
    "receipt_number": string,
    "date": string,
    "time": string
  },
  "items": [{
    "brand": string | null,     // Full brand name, not abbreviated
    "product": string,          // Full product name, not abbreviated
    "product_type": string,     // Generic product type (e.g., toilet paper, pie, bread, salmon)
    "category": string,         // One of: Produce, Bakery, Household, Meat, Seafood, Grocery, Miscellaneous
    "quantity": number | null,  // Use for unit items
    "weight": number | null,    // Use for weighted items (in pounds)
    "unit": "pounds" | "each",
    "unit_price": number,
    "total_price": number,
    "is_organic": boolean,
    "savings": number | null
  }],
  "totals": {
    "subtotal": number,
    "total_savings": number,
    "tax": [{
      "rate": number,
      "amount": number
    }],
    "total": number
  },
  "payment": {
    "method": string,
    "card_last_four": string | null,
    "amount": number
  }
}

Rules:
1. Expand all abbreviations into full names
2. Use generic types for product_type field
3. Include every item from the receipt
4. Double-check all prices and calculations"""
                    },
                    {
                        "role": "user",
                        "content": f"Convert this receipt text to structured JSON:\n\n{text}"
                    }
                ],
                max_tokens=4096,
                response_format={ "type": "json_object" }
            )
            
            data = json.loads(response.choices[0].message.content)
            return ProcessingResult(success=True, data=data)
            
        except Exception as e:
            return ProcessingResult(success=False, error=f"Failed to structure data: {str(e)}")

def print_summary(results: ProcessingResult) -> None:
    """Print receipt summary."""
    if not results.success:
        print(f"\nError: {results.error}")
        return
        
    data = results.data
    print("\nReceipt Summary:")
    print("-" * 50)
    
    # Metadata
    meta = data.get('metadata', {})
    print(f"Store: {meta.get('store', 'N/A')}")
    print(f"Date: {meta.get('date', 'N/A')} {meta.get('time', '')}")
    print(f"Receipt #: {meta.get('receipt_number', 'N/A')}")
    
    # Items
    items = data.get('items', [])
    categories = {}
    organic_count = 0
    product_types = set()
    
    for item in items:
        cat = item.get('category', 'Unknown')
        categories[cat] = categories.get(cat, 0) + item.get('total_price', 0)
        if item.get('is_organic'):
            organic_count += 1
        if item.get('product_type'):
            product_types.add(item.get('product_type'))
    
    print(f"\nItems: {len(items)} (Organic: {organic_count})")
    print("\nProduct Types Found:")
    for ptype in sorted(product_types):
        print(f"- {ptype}")
        
    print("\nCategory Breakdown:")
    for cat, total in sorted(categories.items()):
        print(f"{cat}: ${total:.2f}")
    
    # Totals
    totals = data.get('totals', {})
    tax_entries = totals.get('tax', [])
    if isinstance(tax_entries, list):
        tax_total = sum(t.get('amount', 0) for t in tax_entries)
    else:
        tax_total = float(tax_entries) if tax_entries else 0
    
    print(f"\nSubtotal: ${totals.get('subtotal', 0):.2f}")
    print(f"Tax: ${tax_total:.2f}")
    print(f"Total: ${totals.get('total', 0):.2f}")
    
    payment = data.get('payment', {})
    method = payment.get('method', 'N/A')
    last_four = payment.get('card_last_four')
    if last_four:
        print(f"\nPaid with: {method} ending in {last_four}")
    else:
        print(f"\nPaid with: {method}")

def process_folder(folder_path: str, api_key: str) -> None:
    """Process a receipt folder and save results."""
    path = Path(folder_path)
    if not path.exists():
        print(f"Error: Directory not found: {path}")
        return

    # Find all image files
    image_files = sorted(path.glob('*.jpg'))  # Sort to ensure consistent order
    if not image_files:
        print(f"Error: No JPG images found in {path}")
        return
    
    print(f"\nFound {len(image_files)} receipt image(s) in: {path}")
    processor = ReceiptProcessor(api_key)
    
    # Process image(s)
    image_paths = [str(f) for f in image_files]
    results = processor.transcribe_images(image_paths)
    
    # Create analysis subdirectory and save results
    if results.success:
        output_dir = path / "analysis"
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "receipt_analysis.json"
        
        with open(json_path, 'w') as f:
            json.dump(results.data, f, indent=2)
        print(f"\nResults saved to: {json_path}")
    
    print_summary(results)

def main():
    parser = argparse.ArgumentParser(description='Process receipt directory')
    parser.add_argument('receipt_dir', help='Path to receipt directory')
    parser.add_argument('--env', help='Path to .env file', default='.env')
    
    args = parser.parse_args()
    
    # Load environment
    env_path = Path(args.env)
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        return
        
    load_dotenv(env_path)
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env file")
        return

    process_folder(args.receipt_dir, api_key)

if __name__ == "__main__":
    main()