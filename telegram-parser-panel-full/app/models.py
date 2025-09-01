from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    api_id = Column(Integer, nullable=False)
    api_hash = Column(String(128), nullable=False)
    phone = Column(String(64), nullable=False, unique=True)
    string_session = Column(String(4096), nullable=True)
    phone_code_hash = Column(String(256), nullable=True)
    is_ready = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("Member", back_populates="account", cascade="all, delete-orphan")

class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)

    tg_user_id = Column(Integer, index=True, nullable=False)
    username = Column(String(128), index=True)
    first_name = Column(String(256))
    last_name = Column(String(256))
    is_bot = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)

    group_id = Column(String(256), index=True)
    group_title = Column(String(512))

    crawled_at = Column(DateTime(timezone=True), server_default=func.now())

    account = relationship("Account", back_populates="members")

    __table_args__ = (
        UniqueConstraint('account_id', 'tg_user_id', 'group_id', name='uq_member_account_user_group'),
    )
