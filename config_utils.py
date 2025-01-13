import yaml
from pathlib import Path
import streamlit as st

def load_config() -> dict:
    """Load configuration from config.yaml"""
    config_path = Path("config.yaml")
    if not config_path.exists():
        # Create default config if it doesn't exist
        default_config = {
            'storage': {
                'receipts_dir': str(Path.home() / "ReceiptSage/data/receipts"),
                'database_path': 'receipts.db'
            },
            'display': {
                'max_image_width': 800,
                'max_receipt_history': 50
            }
        }
        with open(config_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)
        return default_config
    
    with open(config_path) as f:
        return yaml.safe_load(f)

def setup_storage(config: dict) -> Path:
    """Setup storage directories based on configuration"""
    receipts_dir = Path(config['storage']['receipts_dir']).expanduser().absolute()
    
    if not receipts_dir.exists():
        st.write(f"Creating directory: {receipts_dir}")
        receipts_dir.mkdir(parents=True, exist_ok=True)
    else:
        st.write(f"Using existing directory: {receipts_dir}")
    
    return receipts_dir