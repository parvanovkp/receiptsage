from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker
from models import Receipt, ReceiptItem, ReceiptTax
import streamlit as st
from pathlib import Path
from import_receipts import import_receipt
from config_utils import load_config, setup_storage

def delete_receipts(session, receipt_ids):
    """Delete receipts and their associated data from the database"""
    try:
        # Delete related items and taxes first (due to foreign key constraints)
        session.query(ReceiptItem).filter(ReceiptItem.receipt_id.in_(receipt_ids)).delete(synchronize_session=False)
        session.query(ReceiptTax).filter(ReceiptTax.receipt_id.in_(receipt_ids)).delete(synchronize_session=False)
        
        # Delete the receipts
        session.query(Receipt).filter(Receipt.id.in_(receipt_ids)).delete(synchronize_session=False)
        
        session.commit()
        return True, "Successfully deleted receipts"
    except Exception as e:
        session.rollback()
        return False, str(e)

def reimport_receipt(session, receipt_id):
    """Reimport a receipt from its JSON file"""
    try:
        receipt = session.query(Receipt).filter_by(id=receipt_id).first()
        if not receipt or not receipt.json_path:
            return False, "Receipt or JSON file not found"
            
        # Delete existing items and taxes
        session.query(ReceiptItem).filter_by(receipt_id=receipt_id).delete()
        session.query(ReceiptTax).filter_by(receipt_id=receipt_id).delete()
        
        # Reimport from JSON
        json_path = Path(receipt.json_path)
        if not json_path.exists():
            return False, f"JSON file not found: {json_path}"
            
        # Reimport the receipt
        import_receipt(session, json_path)
        
        session.commit()
        return True, "Successfully reimported receipt"
    except Exception as e:
        session.rollback()
        return False, str(e)

def delete_analysis_folder(receipt_json_path: str) -> tuple[bool, str]:
    """Delete the analysis folder for a specific receipt"""
    try:
        if not receipt_json_path:
            return False, "No JSON path provided"
            
        analysis_dir = Path(receipt_json_path).parent
        if analysis_dir.exists():
            for file in analysis_dir.iterdir():
                file.unlink()
            analysis_dir.rmdir()
            return True, "Analysis folder deleted"
        return False, "Analysis folder not found"
    except Exception as e:
        return False, f"Error deleting analysis folder: {str(e)}"

def delete_all_analysis_folders(base_dir: str) -> tuple[int, list[str]]:
    """Delete all analysis folders in the receipts directory"""
    base_path = Path(base_dir)
    analysis_dirs = list(base_path.glob("*/analysis"))
    deleted_count = 0
    errors = []
    
    for analysis_dir in analysis_dirs:
        try:
            for file in analysis_dir.iterdir():
                file.unlink()
            analysis_dir.rmdir()
            deleted_count += 1
        except Exception as e:
            errors.append(f"Error with {analysis_dir}: {str(e)}")
    
    return deleted_count, errors

def display_database_management(session):
    """Display the database management interface"""
    st.header("Database Management")
    
    # Add tabs for different management functions
    tab1, tab2 = st.tabs(["Receipt Records", "Analysis Files"])
    
    with tab1:
        # Load all receipts
        receipts = session.query(
            Receipt.id,
            Receipt.date,
            Receipt.store_normalized,
            Receipt.receipt_number,
            Receipt.total,
            Receipt.json_path
        ).order_by(Receipt.date.desc()).all()
        
        # Create selection interface
        selected_ids = []
        
        # Display receipts in a table
        st.write("Select receipts to manage:")
        
        columns = ['Select', 'Date', 'Store', 'Receipt #', 'Total', 'Status', 'Actions']
        
        # Create the table header
        cols = st.columns([0.5, 1, 1.5, 1, 1, 1, 1.5])
        for col, column_name in zip(cols, columns):
            col.write(column_name)
        
        # Display each receipt
        for receipt in receipts:
            cols = st.columns([0.5, 1, 1.5, 1, 1, 1, 1.5])
            
            # Checkbox for selection
            selected = cols[0].checkbox(
                "Select receipt",  # Add a label
                key=f"select_{receipt.id}",
                label_visibility="collapsed"  # Hide the label but keep it accessible
            )
            if selected:
                selected_ids.append(receipt.id)
            
            # Display receipt info
            cols[1].write(receipt.date.strftime('%Y-%m-%d'))
            cols[2].write(receipt.store_normalized)
            cols[3].write(receipt.receipt_number)
            cols[4].write(f"${receipt.total:.2f}")
            
            # Status
            if receipt.json_path and Path(receipt.json_path).exists():
                cols[5].success("Valid")
            else:
                cols[5].error("Invalid")
            
            # Individual actions
            if cols[6].button("Delete", key=f"delete_{receipt.id}"):
                if st.session_state.get('confirm_delete') != receipt.id:
                    st.session_state.confirm_delete = receipt.id
                    st.warning(f"Are you sure you want to delete this receipt from {receipt.store_normalized}?")
                    if st.button("Yes, Delete", key=f"confirm_{receipt.id}"):
                        success, message = delete_receipts(session, [receipt.id])
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
        
        # Bulk actions
        if selected_ids:
            st.divider()
            col1, col2 = st.columns(2)
            
            if col1.button(f"Delete Selected ({len(selected_ids)} receipts)"):
                if st.session_state.get('confirm_bulk_delete') != True:
                    st.session_state.confirm_bulk_delete = True
                    st.warning(f"Are you sure you want to delete {len(selected_ids)} receipts?")
                    if st.button("Yes, Delete Selected"):
                        success, message = delete_receipts(session, selected_ids)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
            
            if col2.button(f"Reimport Selected ({len(selected_ids)} receipts)"):
                progress_bar = st.progress(0)
                for i, receipt_id in enumerate(selected_ids):
                    success, message = reimport_receipt(session, receipt_id)
                    if success:
                        st.success(f"Reimported receipt {receipt_id}")
                    else:
                        st.error(f"Failed to reimport receipt {receipt_id}: {message}")
                    progress_bar.progress((i + 1) / len(selected_ids))
                st.rerun()

    with tab2:
        st.subheader("Analysis Files Management")
        st.warning("⚠️ Deleting analysis files will require reprocessing receipts to regenerate them.")
        
        # Get base directory from config
        config = load_config()
        base_dir = setup_storage(config)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("Delete ALL Analysis Folders", type="secondary"):
                if st.session_state.get('confirm_delete_all_analysis') != True:
                    st.session_state.confirm_delete_all_analysis = True
                    st.warning("Are you sure you want to delete ALL analysis folders? This cannot be undone.")
                    if st.button("Yes, Delete All Analysis"):
                        deleted_count, errors = delete_all_analysis_folders(str(base_dir))
                        if errors:
                            st.error(f"Encountered {len(errors)} errors while deleting folders")
                            for error in errors:
                                st.error(error)
                        st.success(f"Successfully deleted {deleted_count} analysis folders")
                        st.rerun()
        with col2:
            st.info("This will delete all analysis folders, allowing for complete reprocessing of receipts.")
        
        st.divider()
        
        # Show individual receipt analysis management
        st.subheader("Individual Receipt Analysis")
        
        # Load receipts with analysis folders
        receipts = session.query(
            Receipt.id,
            Receipt.date,
            Receipt.store_normalized,
            Receipt.receipt_number,
            Receipt.json_path
        ).filter(Receipt.json_path.isnot(None)).order_by(Receipt.date.desc()).all()
        
        # Create a table
        for receipt in receipts:
            cols = st.columns([2, 2, 2, 1])
            
            # Display receipt info
            cols[0].write(receipt.date.strftime('%Y-%m-%d'))
            cols[1].write(receipt.store_normalized)
            
            # Check if analysis folder exists
            analysis_exists = Path(receipt.json_path).parent.exists() if receipt.json_path else False
            if analysis_exists:
                cols[2].success("Analysis Present")
                if cols[3].button("Delete Analysis", key=f"del_analysis_{receipt.id}"):
                    success, message = delete_analysis_folder(receipt.json_path)
                    if success:
                        st.success(f"Deleted analysis for receipt from {receipt.store_normalized}")
                        st.rerun()
                    else:
                        st.error(message)
            else:
                cols[2].error("No Analysis")
                cols[3].empty()  # Empty column since there's no analysis to delete