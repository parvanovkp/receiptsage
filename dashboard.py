import streamlit as st 
import pandas as pd
import json
import os
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from models import Receipt, ReceiptItem, ReceiptTax
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path
from receipt_processor import ReceiptProcessor, ProcessingResult, process_folder
from import_receipts import import_receipt
from store_utils import normalize_store_name
from dotenv import load_dotenv
import yaml
from incremental_import import find_unprocessed_receipts, find_unimported_receipts

# Load environment variables
load_dotenv()

# Configure Streamlit page
st.set_page_config(
    page_title="Receipt Manager",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    # Expand user home directory and make path absolute
    receipts_dir = Path(config['storage']['receipts_dir']).expanduser().absolute()
    
    # Create full path if it doesn't exist
    if not receipts_dir.exists():
        st.write(f"Creating directory: {receipts_dir}")
        receipts_dir.mkdir(parents=True, exist_ok=True)
    else:
        st.write(f"Using existing directory: {receipts_dir}")
    
    return receipts_dir

def create_session():
    """Create database session with initialization if needed"""
    from models import Base  # Import the Base class that contains all model definitions
    
    # Create engine and initialize database if needed
    engine = create_engine('sqlite:///receipts.db')
    Base.metadata.create_all(engine)  # This creates tables if they don't exist
    
    # Create session
    Session = sessionmaker(bind=engine)
    return Session()

def init_dashboard():
    """Initialize the dashboard and handle empty database state"""
    session = create_session()
    try:
        # Check if we have any data
        receipt_count = session.query(Receipt).count()
        if receipt_count == 0:
            st.info("No receipts found in database. Please upload some receipts to get started!")
    except Exception as e:
        st.error(f"Error connecting to database: {str(e)}")
    finally:
        session.close()
    return session

def load_overall_stats(session, start_date=None, end_date=None, selected_stores=None):
    """Load overall statistics with filtering"""
    query = session.query(Receipt)
    
    if start_date:
        query = query.filter(Receipt.date >= start_date)
    if end_date:
        query = query.filter(Receipt.date <= end_date)
    if selected_stores:
        query = query.filter(Receipt.store_normalized.in_(selected_stores))
    
    stats = {
        'total_receipts': query.count(),
        'total_spent': query.with_entities(func.sum(Receipt.total)).scalar() or 0,
        'total_saved': query.with_entities(func.sum(Receipt.total_savings)).scalar() or 0,
        'avg_receipt': query.with_entities(func.avg(Receipt.total)).scalar() or 0,
        'unique_stores': query.with_entities(func.count(func.distinct(Receipt.store_normalized))).scalar() or 0
    }
    return stats

def load_store_spending(session, start_date=None, end_date=None):
    """Load spending by store with date filtering"""
    query = session.query(
        Receipt.store_normalized,
        func.date(Receipt.date).label('date'),
        func.sum(Receipt.total).label('daily_total')
    )
    
    if start_date:
        query = query.filter(Receipt.date >= start_date)
    if end_date:
        query = query.filter(Receipt.date <= end_date)
    
    query = query.group_by(
        Receipt.store_normalized,
        func.date(Receipt.date)
    ).order_by(func.date(Receipt.date))
    
    df = pd.read_sql(query.statement, session.bind)
    df['date'] = pd.to_datetime(df['date'])
    return df

def load_category_stats(session, start_date=None, end_date=None, selected_stores=None):
    """Load spending by category with filtering"""
    query = session.query(
        ReceiptItem.category,
        func.sum(ReceiptItem.total_price).label('total_spent'),
        func.count(ReceiptItem.id).label('item_count')
    ).join(Receipt)  # Join with Receipt to access date and store
    
    if start_date:
        query = query.filter(Receipt.date >= start_date)
    if end_date:
        query = query.filter(Receipt.date <= end_date)
    if selected_stores:
        query = query.filter(Receipt.store_normalized.in_(selected_stores))
    
    query = query.group_by(ReceiptItem.category)
    
    return pd.read_sql(query.statement, session.bind)

def load_receipt_details(session, start_date=None, end_date=None, selected_stores=None, limit=50):
    """Load recent receipt details with filtering"""
    query = session.query(
        Receipt.date,
        Receipt.store_normalized,
        Receipt.total,
        Receipt.json_path,
        Receipt.receipt_number
    )
    
    if start_date:
        query = query.filter(Receipt.date >= start_date)
    if end_date:
        query = query.filter(Receipt.date <= end_date)
    if selected_stores:
        query = query.filter(Receipt.store_normalized.in_(selected_stores))
    
    query = query.order_by(Receipt.date.desc()).limit(limit)
    return pd.read_sql(query.statement, session.bind)

def load_day_of_week_stats(session, start_date=None, end_date=None, selected_stores=None):
    """Load spending patterns by day of week with filtering"""
    query = session.query(
        func.strftime('%w', Receipt.date).label('day_of_week'),
        func.sum(Receipt.total).label('total_spent'),
        func.count(Receipt.id).label('visit_count'),
        func.avg(Receipt.total).label('avg_spend')
    )
    
    if start_date:
        query = query.filter(Receipt.date >= start_date)
    if end_date:
        query = query.filter(Receipt.date <= end_date)
    if selected_stores:
        query = query.filter(Receipt.store_normalized.in_(selected_stores))
    
    query = query.group_by('day_of_week')
    
    df = pd.read_sql(query.statement, session.bind)
    
    # Convert numeric day to name
    days = {
        '0': 'Sunday',
        '1': 'Monday',
        '2': 'Tuesday',
        '3': 'Wednesday',
        '4': 'Thursday',
        '5': 'Friday',
        '6': 'Saturday'
    }
    df['day_name'] = df['day_of_week'].map(days)
    return df

def load_category_by_store_stats(session, start_date=None, end_date=None, selected_stores=None):
    """Load spending by category for each store with filtering"""
    query = session.query(
        Receipt.store_normalized,
        ReceiptItem.category,
        func.sum(ReceiptItem.total_price).label('total_spent'),
        func.count(ReceiptItem.id).label('item_count')
    ).join(ReceiptItem)
    
    if start_date:
        query = query.filter(Receipt.date >= start_date)
    if end_date:
        query = query.filter(Receipt.date <= end_date)
    if selected_stores:
        query = query.filter(Receipt.store_normalized.in_(selected_stores))
    
    query = query.group_by(
        Receipt.store_normalized,
        ReceiptItem.category
    )
    
    df = pd.read_sql(query.statement, session.bind)
    # Pivot the data for the heatmap
    pivot_df = df.pivot(
        index='store_normalized',
        columns='category',
        values='total_spent'
    ).fillna(0)
    return pivot_df

def create_spending_trend_chart(spending_data, selected_stores):
    """Create the spending trends chart with moving averages"""
    fig = px.line(spending_data, 
                  x='date',
                  y='daily_total',
                  color='store_normalized',
                  title='Daily Spending by Store',
                  labels={
                      'date': 'Date',
                      'daily_total': 'Daily Spend ($)',
                      'store_normalized': 'Store'
                  })
    
    # Improve layout
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Daily Spend ($)",
        legend_title="Store",
        xaxis_tickformat='%B %d, %Y',
        hovermode='x unified'
    )
    
    # Add moving averages
    for store in selected_stores:
        store_data = spending_data[spending_data['store_normalized'] == store]
        if not store_data.empty:
            ma = store_data['daily_total'].rolling(window=7).mean()
            fig.add_trace(
                go.Scatter(x=store_data['date'],
                          y=ma,
                          name=f'{store} (7-day MA)',
                          line=dict(dash='dash'))
            )
    
    return fig

def create_day_of_week_chart(dow_data):
    """Create bar chart for day of week analysis"""
    fig = go.Figure()
    
    # Add total spending bars
    fig.add_trace(go.Bar(
        x=dow_data['day_name'],
        y=dow_data['total_spent'],
        name='Total Spent',
        yaxis='y',
        marker_color='lightblue'
    ))
    
    # Add visit count line
    fig.add_trace(go.Scatter(
        x=dow_data['day_name'],
        y=dow_data['visit_count'],
        name='Visit Count',
        yaxis='y2',
        line=dict(color='red', width=2)
    ))
    
    # Update layout
    fig.update_layout(
        title='Spending and Visit Patterns by Day of Week',
        xaxis_title='Day of Week',
        yaxis_title='Total Spent ($)',
        yaxis2=dict(
            title='Number of Visits',
            overlaying='y',
            side='right'
        ),
        hovermode='x unified',
        barmode='group'
    )
    
    return fig

def create_category_store_heatmap(pivot_data):
    """Create heatmap for category spending by store"""
    fig = px.imshow(
        pivot_data,
        labels=dict(
            x='Category',
            y='Store',
            color='Spending ($)'
        ),
        aspect='auto',
        color_continuous_scale='Viridis'
    )
    
    fig.update_layout(
        title='Category Spending by Store',
        xaxis_title='Category',
        yaxis_title='Store',
        height=400
    )
    
    return fig

def display_receipt_items(items_df):
    """Display receipt items in a formatted table"""
    if not items_df.empty:
        # Select and rename columns for display
        display_cols = {
            'product': 'Product',
            'quantity': 'Qty',
            'unit_price': 'Unit Price',
            'total_price': 'Total',
            'category': 'Category'
        }
        
        display_df = items_df[display_cols.keys()].copy()
        display_df.columns = display_cols.values()
        
        # Format currency columns
        for col in ['Unit Price', 'Total']:
            display_df[col] = display_df[col].apply(lambda x: f"${x:.2f}")
            
        st.dataframe(display_df, use_container_width=True)

def find_receipt_images(json_path: str) -> list[Path]:
    """Find receipt images in the same directory as the JSON file"""
    if not json_path:
        return []
        
    try:
        # Load JSON to get the image path
        with open(json_path) as f:
            data = json.load(f)
        
        image_path = data.get('metadata', {}).get('image_path')
        if image_path and Path(image_path).exists():
            return [Path(image_path)]
    except Exception:
        pass
    
    # Fallback: look for images in receipt directory
    receipt_dir = Path(json_path).parent.parent
    return sorted(receipt_dir.glob('*.jpg'))

def handle_receipt_upload(uploaded_files):
    """Process uploaded receipt files with improved handling"""
    st.write("Starting receipt upload handler")
    
    if not uploaded_files:
        return
    
    # Load configuration
    config = load_config()
    
    # Check OpenAI API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        st.error("OpenAI API key not found. Please check your .env file.")
        return
    
    # Setup storage
    base_dir = setup_storage(config)
    st.write(f"Using receipts directory: {base_dir}")
    
    # Process each receipt
    for uploaded_file in uploaded_files:
        with st.status(f"Processing {uploaded_file.name}...", expanded=True) as status:
            try:
                # Create receipt directory with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                receipt_dir = base_dir / f"receipt_{timestamp}"
                st.write(f"Creating receipt directory: {receipt_dir}")
                receipt_dir.mkdir(exist_ok=True)
                
                # Save uploaded file with original name
                file_path = receipt_dir / uploaded_file.name
                st.write(f"Saving file to: {file_path}")
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                status.write(f"File saved to {receipt_dir}")
                
                # Process the receipt
                processor = ReceiptProcessor(api_key)
                results = processor.process_receipt(str(file_path))
                
                if results.success:
                    # Save the analysis results
                    analysis_dir = receipt_dir / "analysis"
                    analysis_dir.mkdir(exist_ok=True)
                    json_path = analysis_dir / "receipt_analysis.json"
                    
                    # Add image path to the JSON data
                    results.data['metadata']['image_path'] = str(file_path)
                    
                    with open(json_path, 'w') as f:
                        json.dump(results.data, f, indent=2)
                    
                    status.write("Receipt processed, importing to database...")
                    
                    # Import to database
                    session = create_session()
                    try:
                        receipt = import_receipt(session, json_path)
                        
                        # Update directory name with actual receipt date if available
                        try:
                            receipt_date = datetime.strptime(results.data['metadata']['date'], "%m/%d/%Y")
                            new_receipt_id = f"receipt_{receipt_date.strftime('%Y%m%d')}_{timestamp[-6:]}"
                            new_receipt_dir = base_dir / new_receipt_id
                            
                            if new_receipt_dir != receipt_dir:
                                receipt_dir.rename(new_receipt_dir)
                                # Update the file paths in database
                                receipt.json_path = str(new_receipt_dir / "analysis/receipt_analysis.json")
                                session.commit()
                                status.write(f"Updated directory name to include receipt date: {new_receipt_id}")
                        except Exception as e:
                            status.write(f"Note: Couldn't update directory name with receipt date: {str(e)}")

                        status.update(
                            label=f"Successfully processed receipt from {receipt.store}",
                            state="complete",
                            expanded=False
                        )
                    except Exception as e:
                        error_msg = f"Error importing receipt: {str(e)}"
                        status.update(label=error_msg, state="error")
                        st.error(error_msg)
                    finally:
                        session.close()
                else:
                    error_msg = f"Error processing receipt: {results.error}"
                    status.update(label=error_msg, state="error")
                    st.error(error_msg)
            
            except Exception as e:
                error_msg = f"Error processing file: {str(e)}"
                status.update(label=error_msg, state="error")
                st.error(error_msg)

def import_existing_receipts(base_dir: str | Path) -> tuple[int, int]:
    """Import all existing receipts from the directory"""
    # Ensure base_dir is a Path object
    base_dir = Path(base_dir)
    
    if not base_dir.exists():
        st.error(f"Directory not found: {base_dir}")
        return 0, 0
        
    session = create_session()
    try:
        # Find receipts needing processing
        unprocessed = find_unprocessed_receipts(str(base_dir))
        processed_count = 0
        imported_count = 0
        
        if unprocessed:
            st.write(f"Found {len(unprocessed)} unprocessed receipt(s)")
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                st.error("OpenAI API key not found. Please check your .env file.")
                return 0, 0
                
            # Process unprocessed receipts
            for directory in unprocessed:
                try:
                    process_folder(str(directory), api_key)
                    processed_count += 1
                except Exception as e:
                    st.error(f"Error processing {directory}: {str(e)}")

        # Find and import any receipts not in database
        unimported = find_unimported_receipts(str(base_dir), session)
        if unimported:
            st.write(f"Found {len(unimported)} receipt(s) to import")
            for json_path in unimported:
                try:
                    receipt = import_receipt(session, json_path)
                    st.write(f"Imported receipt {receipt.receipt_number} from {receipt.store}")
                    imported_count += 1
                except Exception as e:
                    st.error(f"Error importing {json_path}: {str(e)}")
        
        return processed_count, imported_count
    finally:
        session.close()

def display_upload_section():
    """Display receipt upload interface with improved feedback"""
    st.header("Upload Receipts")
    
    # Load configuration and setup storage
    config = load_config()
    base_dir = setup_storage(config)
    st.write(f"Receipt storage location: {base_dir}")

    if st.button("Debug Store Names", type="secondary"):
        config = load_config()
        base_dir = setup_storage(config)
        check_stores(base_dir)
    
    # Add import existing receipts button
    col1, col2 = st.columns([2, 3])
    with col1:
        if st.button("Import Existing Receipts", type="secondary"):
            with st.status("Importing existing receipts...", expanded=True) as status:
                processed, imported = import_existing_receipts(base_dir)
                status.update(label=f"Processed {processed} and imported {imported} receipts", state="complete")
                if processed > 0 or imported > 0:
                    st.rerun()
    with col2:
        st.info("Use this to import receipts that are already in the receipts directory")
    
    st.divider()
    
    # File uploader with drag-and-drop
    uploaded_files = st.file_uploader(
        "Drop receipt images here or click to browse",
        accept_multiple_files=True,
        type=['jpg'],
        help="You can upload multiple receipt images at once"
    )
    
    if uploaded_files:
        st.write(f"Number of files selected: {len(uploaded_files)}")
        for file in uploaded_files:
            st.write(f"File name: {file.name}, Size: {file.size} bytes")
            
        col1, col2 = st.columns([1, 4])
        with col1:
            process_button = st.button("Process Receipts", type="primary")
            if process_button:
                st.write("Process button clicked")
                handle_receipt_upload(uploaded_files)
                # After processing new receipts, run incremental import
                with st.status("Running final import check...", expanded=True) as status:
                    _, imported = import_existing_receipts(base_dir)
                    if imported > 0:
                        status.update(label=f"Imported {imported} new receipts", state="complete")
                    else:
                        status.update(label="No additional receipts to import", state="complete")
                st.rerun()  # Refresh the dashboard after processing
        with col2:
            st.write(f"{len(uploaded_files)} files selected for processing")

def check_stores(base_dir: str | Path) -> None:
    """Print out all store names from JSON files"""
    base_dir = Path(base_dir)
    json_files = list(base_dir.glob('*/analysis/receipt_analysis.json'))
    
    st.write(f"Found {len(json_files)} receipt analysis files")
    
    store_counts = {}
    normalized_counts = {}
    
    for json_path in json_files:
        try:
            with open(json_path) as f:
                data = json.load(f)
                store = data['metadata']['store']
                normalized = normalize_store_name(store)
                
                store_counts[store] = store_counts.get(store, 0) + 1
                normalized_counts[normalized] = normalized_counts.get(normalized, 0) + 1
                
                st.write(f"Original: {store}")
                st.write(f"Normalized: {normalized}")
                st.write(f"Location: {data['metadata']['address']}")
                st.write("---")
        except Exception as e:
            st.error(f"Error reading {json_path}: {str(e)}")
    
    st.write("\nStore Counts:")
    for store, count in store_counts.items():
        st.write(f"{store}: {count}")
        
    st.write("\nNormalized Store Counts:")
    for store, count in normalized_counts.items():
        st.write(f"{store}: {count}")

def main():
    st.title("Receipt Analysis Dashboard")
    
    # Add navigation
    page = st.sidebar.radio("Navigation", ["Dashboard", "Upload Receipts"])
    
    session = init_dashboard()
    
    try:
        if page == "Upload Receipts":
            display_upload_section()
        else:
            # Date Range Selector
            st.sidebar.header("Filters")
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)  # Default to last 30 days
            
            start_date = st.sidebar.date_input("Start Date", start_date)
            end_date = st.sidebar.date_input("End Date", end_date)
            
            if start_date > end_date:
                st.error("Error: End date must be after start date")
                return
            
            # Store Selector
            stores = pd.read_sql(
                session.query(Receipt.store_normalized)
                .distinct()
                .statement,
                session.bind
            )
            selected_stores = st.sidebar.multiselect(
                "Select Stores",
                options=stores['store_normalized'].tolist(),
                default=stores['store_normalized'].tolist()
            )
            
            # Overall Statistics
            st.header("Overall Statistics")
            stats = load_overall_stats(session, start_date, end_date, selected_stores)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Receipts", f"{stats['total_receipts']:,}")
                st.metric("Total Spent", f"${stats['total_spent']:,.2f}")
            with col2:
                st.metric("Total Saved", f"${stats['total_saved']:,.2f}")
                st.metric("Average Receipt", f"${stats['avg_receipt']:,.2f}")
            with col3:
                st.metric("Unique Stores", f"{stats['unique_stores']:,}")

            # Spending by Category
            st.header("Spending by Category")
            category_df = load_category_stats(session, start_date, end_date, selected_stores)
            
            fig_category = px.pie(category_df, 
                                values='total_spent', 
                                names='category',
                                title='Spending Distribution by Category')
            st.plotly_chart(fig_category)

            # Day of Week Analysis
            st.header("Shopping Patterns")
            dow_data = load_day_of_week_stats(session, start_date, end_date, selected_stores)
            dow_fig = create_day_of_week_chart(dow_data)
            st.plotly_chart(dow_fig, use_container_width=True)

            # Category by Store Analysis
            st.header("Category Spending by Store")
            category_store_data = load_category_by_store_stats(session, start_date, end_date, selected_stores)
            heatmap_fig = create_category_store_heatmap(category_store_data)
            st.plotly_chart(heatmap_fig, use_container_width=True)
            
            # Spending Trends
            st.header("Spending Trends")
            spending_data = load_store_spending(session, start_date, end_date)
            spending_data = spending_data[spending_data['store_normalized'].isin(selected_stores)]
            
            if not spending_data.empty:
                fig = create_spending_trend_chart(spending_data, selected_stores)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No spending data available for the selected date range and stores.")
            
            # Recent Receipts
            st.header("Recent Receipts")
            receipts_df = load_receipt_details(session, start_date, end_date, selected_stores)
            
            # Display each receipt
            for _, receipt in receipts_df.iterrows():
                receipt_date = pd.to_datetime(receipt['date']).strftime('%Y-%m-%d')
                st.subheader(f"{receipt_date} - {receipt['store_normalized']} - ${receipt['total']:.2f}")
                
                # Each receipt can have two expanders side by side
                col1, col2 = st.columns(2)
                
                with col1:
                    with st.expander("View Items"):
                        if receipt['json_path']:
                            try:
                                with open(receipt['json_path'], 'r') as f:
                                    data = json.load(f)
                                    items_df = pd.DataFrame(data['items'])
                                    display_receipt_items(items_df)
                            except Exception as e:
                                st.error(f"Error loading receipt items: {str(e)}")
                        else:
                            st.warning("Receipt details not available")
                
                with col2:
                    with st.expander("View Images"):
                        try:
                            images = find_receipt_images(receipt['json_path'])
                            if images:
                                for img_path in images:
                                    st.image(str(img_path), caption=img_path.name)
                            else:
                                st.warning("No receipt images found")
                        except Exception as e:
                            st.error(f"Error loading receipt images: {str(e)}")
                
                st.divider()  # Add a line between receipts
    finally:
        session.close()

if __name__ == "__main__":
    main()