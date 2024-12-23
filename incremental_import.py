import os
import json
import argparse
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from models import init_db, Receipt
from import_receipts import import_receipt
from receipt_processor import process_folder
from dotenv import load_dotenv

def find_unprocessed_receipts(base_dir: str) -> list[Path]:
    """
    Find receipt directories that haven't been processed yet
    (those without analysis/receipt_analysis.json)
    """
    base_path = Path(base_dir)
    all_dirs = [d for d in base_path.iterdir() if d.is_dir()]
    unprocessed = []
    
    for directory in all_dirs:
        analysis_file = directory / "analysis" / "receipt_analysis.json"
        if not analysis_file.exists():
            # Check if directory contains any jpg files
            if list(directory.glob("*.jpg")):
                unprocessed.append(directory)
    
    return unprocessed

def find_unimported_receipts(base_dir: str, session) -> list[Path]:
    """
    Find processed receipts that haven't been imported to the database yet
    """
    base_path = Path(base_dir)
    analysis_files = list(base_path.glob("*/analysis/receipt_analysis.json"))
    unimported = []
    
    for analysis_file in analysis_files:
        # Check if this receipt is already in the database
        exists = session.query(Receipt).filter_by(
            json_path=str(analysis_file)
        ).first() is not None
        
        if not exists:
            unimported.append(analysis_file)
    
    return unimported

def process_new_receipts(unprocessed_dirs: list[Path], api_key: str) -> None:
    """
    Run receipt processor on directories containing unprocessed receipts
    """
    for directory in unprocessed_dirs:
        print(f"\nProcessing receipt in: {directory}")
        try:
            process_folder(str(directory), api_key)
        except Exception as e:
            print(f"Error processing {directory}: {str(e)}")

def import_new_receipts(unimported_files: list[Path], session) -> None:
    """
    Import processed receipts into the database
    """
    for json_path in unimported_files:
        print(f"\nImporting receipt: {json_path}")
        try:
            receipt = import_receipt(session, json_path)
            print(f"Imported receipt {receipt.receipt_number} from {receipt.store}")
        except Exception as e:
            print(f"Error importing {json_path}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Process and import new receipts')
    parser.add_argument('receipts_dir', help='Base directory containing receipt folders')
    parser.add_argument('--env', help='Path to .env file', default='.env')
    parser.add_argument('--db', help='Path to database file', default='receipts.db')
    
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

    # Initialize database connection
    engine = init_db(args.db)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Find receipts needing processing
        unprocessed = find_unprocessed_receipts(args.receipts_dir)
        if unprocessed:
            print(f"\nFound {len(unprocessed)} unprocessed receipt(s)")
            process_new_receipts(unprocessed, api_key)
        else:
            print("\nNo new receipts to process")

        # Find processed receipts needing import
        unimported = find_unimported_receipts(args.receipts_dir, session)
        if unimported:
            print(f"\nFound {len(unimported)} receipt(s) to import")
            import_new_receipts(unimported, session)
        else:
            print("\nNo new receipts to import")

    finally:
        session.close()

if __name__ == "__main__":
    main()