from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Receipt(Base):
    __tablename__ = 'receipts'
    
    id = Column(Integer, primary_key=True)
    store = Column(String)
    store_normalized = Column(String)  # Added for store normalization
    json_path = Column(String)         # Added for receipt lookup
    address = Column(String)
    phone = Column(String, nullable=True)
    receipt_number = Column(String)
    date = Column(DateTime)
    total = Column(Float)
    subtotal = Column(Float)
    total_savings = Column(Float)
    total_tax = Column(Float)
    payment_method = Column(String)
    card_last_four = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    items = relationship("ReceiptItem", back_populates="receipt")
    taxes = relationship("ReceiptTax", back_populates="receipt")

class ReceiptItem(Base):
    __tablename__ = 'receipt_items'
    
    id = Column(Integer, primary_key=True)
    receipt_id = Column(Integer, ForeignKey('receipts.id'))
    brand = Column(String, nullable=True)
    product = Column(String)
    product_type = Column(String)
    category = Column(String)
    quantity = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    unit = Column(String)
    unit_price = Column(Float)
    total_price = Column(Float)
    is_organic = Column(Boolean, default=False)
    savings = Column(Float, nullable=True)
    
    # Relationship
    receipt = relationship("Receipt", back_populates="items")

class ReceiptTax(Base):
    __tablename__ = 'receipt_taxes'
    
    id = Column(Integer, primary_key=True)
    receipt_id = Column(Integer, ForeignKey('receipts.id'))
    rate = Column(Float)
    amount = Column(Float)
    
    # Relationship
    receipt = relationship("Receipt", back_populates="taxes")

def init_db(db_path):
    """Initialize the database and create tables"""
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    return engine