from thefuzz import fuzz, process
from typing import Optional, List
from pathlib import Path
import json
import sqlite3

def get_known_stores() -> List[str]:
    """Get list of known store names from the database"""
    try:
        conn = sqlite3.connect('receipts.db')
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT store_normalized FROM receipts WHERE store_normalized IS NOT NULL")
        stores = [row[0] for row in cursor.fetchall()]
        conn.close()
        return stores
    except sqlite3.Error:
        return []

def normalize_store_name(store_name: str, threshold: int = 51) -> Optional[str]:
    """
    Normalize store names using fuzzy string matching
    
    Args:
        store_name: Raw store name to normalize
        threshold: Minimum similarity score (0-100) to consider a match
        
    Returns:
        Normalized store name
    """
    if not store_name:
        return None
    
    # Clean input
    store = store_name.strip()
    
    # Get known stores from database
    known_stores = get_known_stores()
    
    # If no known stores, this is the first one
    if not known_stores:
        return ' '.join(word.capitalize() for word in store.split())
    
    # Find best match among known stores
    best_match, score = process.extractOne(
        store,
        known_stores,
        scorer=fuzz.token_sort_ratio
    )
    
    # If we have a good match, use it
    if score >= threshold:
        return best_match
    
    # If no good match, clean and return as new store
    return ' '.join(word.capitalize() for word in store.split())

def analyze_store_matches(store_name: str, threshold: int = 80) -> dict:
    """
    Analyze potential matches for a store name
    Useful for debugging and tuning the matching
    
    Args:
        store_name: Store name to analyze
        threshold: Similarity threshold
        
    Returns:
        Dict with analysis results
    """
    if not store_name:
        return {}
    
    known_stores = get_known_stores()
    matches = process.extract(
        store_name,
        known_stores,
        scorer=fuzz.token_sort_ratio,
        limit=5
    )
    
    return {
        'input': store_name,
        'normalized': normalize_store_name(store_name, threshold),
        'top_matches': [
            {
                'store': match[0],
                'score': match[1]
            }
            for match in matches
        ]
    }