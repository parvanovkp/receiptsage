import os
import json
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from models import init_db, Receipt, ReceiptItem, ReceiptTax
from store_utils import normalize_store_name

def parse_datetime(date_str, time_str):
    """Parse date and time strings into datetime object"""
    dt_str = f"{date_str} {time_str}"
    return datetime.strptime(dt_str, "%m/%d/%Y %I:%M %p")

def import_receipt(session, json_path):
    """Import a single receipt JSON file into the database"""
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # Create receipt
    metadata = data['metadata']
    totals = data['totals']
    payment = data['payment']
    
    store_name = metadata['store']
    normalized_store = normalize_store_name(store_name)
    
    receipt = Receipt(
        store=store_name,
        store_normalized=normalized_store,
        json_path=str(json_path),
        address=metadata['address'],
        phone=metadata['phone'],
        receipt_number=metadata['receipt_number'],
        date=parse_datetime(metadata['date'], metadata['time']),
        total=totals['total'],
        subtotal=totals['subtotal'],
        total_savings=totals['total_savings'],
        total_tax=sum(tax['amount'] for tax in totals['tax']),
        payment_method=payment['method'],
        card_last_four=payment['card_last_four']
    )
    session.add(receipt)
    
    # Add items
    for item_data in data['items']:
        item = ReceiptItem(
            receipt=receipt,
            brand=item_data['brand'],
            product=item_data['product'],
            product_type=item_data['product_type'],
            category=item_data['category'],
            quantity=item_data['quantity'],
            weight=item_data['weight'],
            unit=item_data['unit'],
            unit_price=item_data['unit_price'],
            total_price=item_data['total_price'],
            is_organic=item_data['is_organic'],
            savings=item_data['savings']
        )
        session.add(item)
    
    # Add taxes
    for tax_data in totals['tax']:
        tax = ReceiptTax(
            receipt=receipt,
            rate=tax_data['rate'],
            amount=tax_data['amount']
        )
        session.add(tax)
    
    session.commit()
    return receipt

def import_all_receipts(db_path, receipts_dir):
    """Import all receipt JSON files from the specified directory"""
    engine = init_db(db_path)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    receipt_paths = Path(receipts_dir).glob('*/analysis/receipt_analysis.json')
    imported_count = 0
    
    for json_path in receipt_paths:
        try:
            receipt = import_receipt(session, json_path)
            print(f"Imported receipt {receipt.receipt_number} from {receipt.store}")
            imported_count += 1
        except Exception as e:
            print(f"Error importing {json_path}: {str(e)}")
    
    print(f"\nSuccessfully imported {imported_count} receipts")
    session.close()

if __name__ == "__main__":
    # Assuming we're running from the project root
    DB_PATH = "receipts.db"
    RECEIPTS_DIR = "data/receipts"
    
    import_all_receipts(DB_PATH, RECEIPTS_DIR)