import os
import json
from openai import OpenAI
from pathlib import Path
from base64 import b64encode
from typing import Dict, Any
from dotenv import load_dotenv

def encode_image(image_path: str) -> str:
    """
    Encode the image file to base64.
    """
    with open(image_path, "rb") as image_file:
        return b64encode(image_file.read()).decode('utf-8')

def clean_json_response(response: str) -> str:
    """
    Clean the response by removing markdown code blocks and any other non-JSON content.
    """
    # Remove markdown code blocks if present
    if response.startswith('```') and response.endswith('```'):
        response = response.split('```')[1]
        if response.startswith('json\n'):
            response = response[5:]
    
    return response.strip()

def analyze_receipt(image_path: str, api_key: str) -> Dict[str, Any]:
    """
    Analyze receipt using GPT-4 Vision.
    """
    client = OpenAI(api_key=api_key)
    
    base64_image = encode_image(image_path)
    
    prompt = """
    Analyze this receipt and extract the information in a clean, normalized JSON format. Please follow these guidelines:

    1. Product names should be:
       - Written in full English (no abbreviations)
       - Split into brand and product where applicable
       - Categorized by department (e.g., Produce, Bakery, etc.)
       - Include whether item is organic or not

    2. Measurements should be separated:
       - For items sold by weight:
         * weight: numerical amount in pounds
         * quantity: should be null
       - For items sold by unit:
         * quantity: number of units
         * weight: should be null
       - Use standard unit names (each, pounds, ounces)

    3. Structure the JSON with these main sections:
       - metadata: store info, date, time, receipt number
       - items: list of purchased items with normalized names
       - totals: all monetary totals including separate tax entries
       - payment: payment method details
       - promotions: any special offers or notices

    4. For each item include:
       - brand: brand name if available (null if generic)
       - product: full product name in plain English
       - category: department/category
       - quantity: numerical amount for unit items (null for weighted items)
       - weight: numerical amount in pounds for weighted items (null for unit items)
       - unit: "each" for items sold by unit, "pounds" for weighted items
       - unit_price: price per unit/pound
       - total_price: total price for item
       - is_organic: boolean
       - savings: any discounts (null if none)

    Return clean JSON without any markdown formatting.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
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

        result = response.choices[0].message.content
        
        # Clean the response
        cleaned_result = clean_json_response(result)
        
        try:
            parsed_data = json.loads(cleaned_result)
            return parsed_data
        except json.JSONDecodeError as e:
            return {
                "error": "Failed to parse JSON response",
                "raw_response": result,
                "parsing_error": str(e)
            }

    except Exception as e:
        return {"error": f"API call failed: {str(e)}"}

def safe_get(obj: dict, *keys, default=None):
    """Safely get nested dictionary values."""
    current = obj
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current

def print_summary(results: dict) -> None:
    """Print a detailed summary of the receipt analysis with robust error handling."""
    try:
        if "error" not in results:
            print("\nReceipt Summary:")
            print("-" * 50)
            
            # Metadata section
            metadata = results.get('metadata', {})
            print(f"Store: {metadata.get('store', 'N/A')}")
            print(f"Location: {metadata.get('location', metadata.get('address', 'N/A'))}")
            print(f"Date: {metadata.get('date', 'N/A')} {metadata.get('time', '')}")
            print(f"Receipt #: {metadata.get('receipt_number', 'N/A')}")
            
            # Purchase details
            items = results.get('items', [])
            print("\nPurchase Details:")
            print(f"Total Items: {len(items)}")
            print(f"Organic Items: {sum(1 for item in items if item.get('is_organic', False))}")
            
            # Category breakdown
            category_totals = {}
            for item in items:
                category = item.get('category', 'Unknown')
                category_totals[category] = category_totals.get(category, 0) + item.get('total_price', 0)
            
            print("\nCategory Breakdown:")
            for category, total in sorted(category_totals.items()):
                print(f"{category}: ${total:.2f}")
            
            # Payment summary
            totals = results.get('totals', {})
            print("\nPayment Summary:")
            print(f"Subtotal: ${totals.get('subtotal', 0):.2f}")
            print(f"Net Sales: ${totals.get('net_sales', 0):.2f}")
            
            # Handle tax array structure
            tax_total = 0
            taxes = totals.get('tax', [])
            if isinstance(taxes, list):
                tax_total = sum(tax.get('amount', 0) for tax in taxes)
            else:
                tax_total = taxes  # If it's a single number

            print(f"Tax: ${tax_total:.2f}")
            print(f"Total: ${totals.get('total', 0):.2f}")
            
            # Payment details
            payment = results.get('payment', {})
            print(f"Paid with: {payment.get('method', 'N/A')} "
                  f"ending in {payment.get('card_last_four', 'N/A')}")
            print("-" * 50)
    except Exception as e:
        print(f"\nError generating summary: {str(e)}")
        print("Raw results:")
        print(json.dumps(results, indent=2))

def main():
    # Get the root directory (assuming the script is in src/scripts)
    root_dir = Path(__file__).parent.parent.parent
    
    # Load .env from root directory
    env_path = root_dir / '.env'
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        return
        
    load_dotenv(env_path)
    
    # Get API key from environment variable
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env file")
        return

    # Path to test image
    image_path = root_dir / "data" / "test_receipts" / "test1.jpg"
    
    if not image_path.exists():
        print(f"Error: Image file not found: {image_path}")
        return

    print(f"Analyzing receipt image: {image_path}")
    print("This may take a few moments...")
    
    # Create output directory if it doesn't exist
    output_dir = root_dir / "data" / "analyzed_receipts"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save results to file
    output_path = output_dir / "receipt_analysis.json"
    
    # Analyze receipt
    results = analyze_receipt(str(image_path), api_key)
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nAnalysis complete! Results saved to: {output_path}")
    
    # Print enhanced summary
    print_summary(results)

if __name__ == "__main__":
    main()