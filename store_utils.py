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

def normalize_store_name(store_name: str, threshold: int = 80) -> Optional[str]:
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
    
    # Clean input - common variations
    store_maps = {
        "Whole Foods Market": ["Whole Foods", "WFM", "Whole Foods Mkt", "WF Market"],
        "Lunardi's": ["Lunardis", "Lunardi", "Lunardi's Market"]
    }
    
    # Clean input name
    store = store_name.strip()
    
    # Direct mapping check
    for normalized_name, variants in store_maps.items():
        if store in variants or store == normalized_name:
            return normalized_name
    
    # Try fuzzy matching with known stores and their variants
    best_score = 0
    best_match = None
    
    for normalized_name, variants in store_maps.items():
        # Check against normalized name
        score = fuzz.token_sort_ratio(store, normalized_name)
        if score > best_score:
            best_score = score
            best_match = normalized_name
            
        # Check against variants
        for variant in variants:
            score = fuzz.token_sort_ratio(store, variant)
            if score > best_score:
                best_score = score
                best_match = normalized_name
    
    # If we have a good match above threshold
    if best_score >= threshold:
        return best_match
    
    # No match found, return cleaned original
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