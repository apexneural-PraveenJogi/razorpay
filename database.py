"""
Database configuration and models using SQLAlchemy with async support.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Integer, DateTime, JSON, Enum as SQLEnum
from datetime import datetime
import enum
from config import settings


# Database engine and session
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


# ============================================================================
# Database Models
# ============================================================================

class PaymentStatus(str, enum.Enum):
    """Payment status enumeration."""
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


class Order(Base):
    """Order model for storing Razorpay orders."""
    __tablename__ = "orders"
    
    id = Column(String, primary_key=True, index=True)  # Razorpay order ID
    amount = Column(Integer, nullable=False)  # Amount in paise
    amount_paid = Column(Integer, default=0)
    amount_due = Column(Integer, nullable=False)
    currency = Column(String, default="INR")
    receipt = Column(String, nullable=True)
    status = Column(String, nullable=False)
    attempts = Column(Integer, default=0)
    notes = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Payment(Base):
    """Payment model for storing Razorpay payments."""
    __tablename__ = "payments"
    
    id = Column(String, primary_key=True, index=True)  # Razorpay payment ID
    order_id = Column(String, nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # Amount in paise
    currency = Column(String, default="INR")
    status = Column(SQLEnum(PaymentStatus), nullable=False)
    method = Column(String, nullable=True)
    description = Column(String, nullable=True)
    razorpay_data = Column(JSON, nullable=True)  # Full Razorpay response
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubscriptionStatus(str, enum.Enum):
    """Subscription status enumeration."""
    CREATED = "created"
    AUTHENTICATED = "authenticated"
    ACTIVE = "active"
    PENDING = "pending"
    HALTED = "halted"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXPIRED = "expired"
    PAUSED = "paused"


class Subscription(Base):
    """Subscription model for storing Razorpay subscriptions."""
    __tablename__ = "subscriptions"
    
    id = Column(String, primary_key=True, index=True)  # Razorpay subscription ID
    plan_id = Column(String, nullable=True, index=True)
    customer_id = Column(String, nullable=True, index=True)
    status = Column(SQLEnum(SubscriptionStatus), nullable=False)
    current_start = Column(DateTime, nullable=True)
    current_end = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    quantity = Column(Integer, default=1)
    notes = Column(JSON, nullable=True)
    charge_at = Column(DateTime, nullable=True)
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)
    auth_attempts = Column(Integer, default=0)
    total_count = Column(Integer, nullable=True)  # Total billing cycles
    paid_count = Column(Integer, default=0)  # Number of successful payments
    razorpay_data = Column(JSON, nullable=True)  # Full Razorpay response
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubscriptionPayment(Base):
    """Subscription payment model for storing subscription invoice payments."""
    __tablename__ = "subscription_payments"
    
    id = Column(String, primary_key=True, index=True)  # Invoice ID or Payment ID
    subscription_id = Column(String, nullable=False, index=True)
    invoice_id = Column(String, nullable=True, index=True)
    payment_id = Column(String, nullable=True, index=True)
    amount = Column(Integer, nullable=False)  # Amount in paise
    currency = Column(String, default="INR")
    status = Column(String, nullable=False)
    description = Column(String, nullable=True)
    billing_period_start = Column(DateTime, nullable=True)
    billing_period_end = Column(DateTime, nullable=True)
    razorpay_data = Column(JSON, nullable=True)  # Full Razorpay response
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WebhookEvent(Base):
    """Webhook event model for storing webhook events."""
    __tablename__ = "webhook_events"
    
    id = Column(String, primary_key=True, index=True)  # Event ID from Razorpay
    entity = Column(String, nullable=False)
    event = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True)
    payload = Column(JSON, nullable=False)
    signature_verified = Column(String, default="false")  # "true" or "false"
    processed = Column(String, default="false")
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# Database Dependency
# ============================================================================

async def get_db() -> AsyncSession:
    """Dependency for getting database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
