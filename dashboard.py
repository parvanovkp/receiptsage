import streamlit as st 
import pandas as pd
import json
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from models import Receipt, ReceiptItem, ReceiptTax
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path

def create_session():
    engine = create_engine('sqlite:///receipts.db')
    Session = sessionmaker(bind=engine)
    return Session()

def load_overall_stats(session):
    """Load overall statistics"""
    stats = {
        'total_receipts': session.query(Receipt).count(),
        'total_spent': session.query(func.sum(Receipt.total)).scalar() or 0,
        'total_saved': session.query(func.sum(Receipt.total_savings)).scalar() or 0,
        'avg_receipt': session.query(func.avg(Receipt.total)).scalar() or 0,
        'unique_stores': session.query(func.count(func.distinct(Receipt.store_normalized))).scalar() or 0
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

def load_category_stats(session):
    """Load spending by category"""
    query = session.query(
        ReceiptItem.category,
        func.sum(ReceiptItem.total_price).label('total_spent'),
        func.count(ReceiptItem.id).label('item_count')
    ).group_by(ReceiptItem.category)
    
    return pd.read_sql(query.statement, session.bind)

def load_receipt_details(session, limit=50):
    """Load recent receipt details for the table view"""
    query = session.query(
        Receipt.date,
        Receipt.store_normalized,
        Receipt.total,
        Receipt.json_path,
        Receipt.receipt_number
    ).order_by(Receipt.date.desc()).limit(limit)
    return pd.read_sql(query.statement, session.bind)

def load_day_of_week_stats(session):
    """Load spending patterns by day of week"""
    query = session.query(
        func.strftime('%w', Receipt.date).label('day_of_week'),
        func.sum(Receipt.total).label('total_spent'),
        func.count(Receipt.id).label('visit_count'),
        func.avg(Receipt.total).label('avg_spend')
    ).group_by('day_of_week')
    
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

def load_category_by_store_stats(session):
    """Load spending by category for each store"""
    query = session.query(
        Receipt.store_normalized,
        ReceiptItem.category,
        func.sum(ReceiptItem.total_price).label('total_spent'),
        func.count(ReceiptItem.id).label('item_count')
    ).join(ReceiptItem
    ).group_by(
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

def find_receipt_images(json_path):
    """Find receipt images in the same directory as the JSON file"""
    receipt_dir = Path(json_path).parent.parent
    return sorted(receipt_dir.glob('*.jpg'))

def main():
    st.title("Receipt Analysis Dashboard")
    
    session = create_session()
    
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
    stats = load_overall_stats(session)
    
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
    category_df = load_category_stats(session)
    
    fig_category = px.pie(category_df, 
                         values='total_spent', 
                         names='category',
                         title='Spending Distribution by Category')
    st.plotly_chart(fig_category)

    # Day of Week Analysis
    st.header("Shopping Patterns")
    dow_data = load_day_of_week_stats(session)
    dow_fig = create_day_of_week_chart(dow_data)
    st.plotly_chart(dow_fig, use_container_width=True)
    
    # Category by Store Analysis
    st.header("Category Spending by Store")
    category_store_data = load_category_by_store_stats(session)
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
    receipts_df = load_receipt_details(session)
    
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
    
    session.close()

if __name__ == "__main__":
    main()