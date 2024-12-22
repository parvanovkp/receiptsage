from store_utils import normalize_store_name, analyze_store_matches

# Test cases
test_stores = [
    "Whole Foods",
    "WholeFoods Market",
    "Whole Foods Market",
    "WFM",
    "WHOLE FOODS MKT",
    "Wholefoods",
    "WF Market",
    "Whole Food Market",  # Common typo
    "Whole Foods Markets",  # Plural variation
    "WholeFoods Mkt",
    "WHOLEFOODS",
    "W F Market"
]

def test_normalization():
    print("Testing store name normalization:\n")
    
    for store in test_stores:
        normalized = normalize_store_name(store)
        print(f"Original: {store}")
        print(f"Normalized: {normalized}")
        print("-" * 50)

def test_analysis():
    print("\nDetailed analysis of matching:\n")
    
    for store in test_stores:
        analysis = analyze_store_matches(store)
        print(analysis)
        print(f"\nAnalyzing: {store}")
        print(f"Normalized to: {analysis['normalized']}")
        print("\nTop matches:")
        for match in analysis['top_matches']:
            print(f"- {match['store']} (score: {match['score']})")
        print("-" * 50)

if __name__ == "__main__":
    test_normalization()
    test_analysis()