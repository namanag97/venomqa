"""
SQLAlchemy models for the Full-Featured App.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)


class Item(Base, TimestampMixin):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, default=1, nullable=False)


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    total = Column(Float, nullable=False)
    shipping_address = Column(Text, nullable=False)
    task_id = Column(String(255), nullable=True)


class SearchIndex(Base):
    __tablename__ = "search_index"

    id = Column(Integer, primary_key=True, index=True)
    document_type = Column(String(50), index=True, nullable=False)
    document_id = Column(String(100), index=True, nullable=False)
    content = Column(Text, nullable=False)
    metadata = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String(255), nullable=False)
    recipient = Column(String(255), nullable=False, index=True)
    subject = Column(String(500), nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FileUpload(Base, TimestampMixin):
    __tablename__ = "file_uploads"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    content_type = Column(String(255), nullable=False)
    size = Column(Integer, nullable=False)
    storage_path = Column(String(1000), nullable=False)
    uploaded_by = Column(Integer, nullable=True)


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(500), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def init_db(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
