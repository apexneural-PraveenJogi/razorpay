"""
Pydantic schemas for request/response validation.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator


# ============================================================================
# Order Creation Schemas
# ============================================================================

class OrderCreateRequest(BaseModel):
    """Request schema for creating an order."""
    amount: float = Field(..., gt=0, description="Amount in rupees")
    currency: str = Field(default="INR", description="Currency code")
    receipt: Optional[str] = Field(None, description="Receipt identifier")
    notes: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    @validator("amount")
    def validate_amount(cls, v):
        """Convert rupees to paise and validate."""
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return int(v * 100)  # Convert to paise
    
    class Config:
        json_schema_extra = {
            "example": {
                "amount": 100.0,
                "currency": "INR",
                "receipt": "receipt_001",
                "notes": {
                    "customer_name": "John Doe",
                    "order_id": "order_123"
                }
            }
        }


class OrderCreateResponse(BaseModel):
    """Response schema for order creation."""
    id: str = Field(..., description="Razorpay order ID")
    entity: str
    amount: int = Field(..., description="Amount in paise")
    amount_paid: int
    amount_due: int
    currency: str
    receipt: Optional[str]
    status: str
    attempts: int
    notes: Optional[Dict[str, Any]] = None
    created_at: int
    
    @validator("notes", pre=True)
    def validate_notes(cls, v):
        """Handle notes as empty list or dict."""
        if v is None or v == []:
            return None
        if isinstance(v, dict):
            return v
        return None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "order_abc123",
                "entity": "order",
                "amount": 10000,
                "amount_paid": 0,
                "amount_due": 10000,
                "currency": "INR",
                "receipt": "receipt_001",
                "status": "created",
                "attempts": 0,
                "notes": {},
                "created_at": 1234567890
            }
        }


# ============================================================================
# Payment Verification Schemas
# ============================================================================

class PaymentVerifyRequest(BaseModel):
    """Request schema for payment verification."""
    order_id: str = Field(..., description="Razorpay order ID")
    payment_id: str = Field(..., description="Razorpay payment ID")
    signature: str = Field(..., description="Payment signature")
    
    class Config:
        json_schema_extra = {
            "example": {
                "order_id": "order_abc123",
                "payment_id": "pay_xyz789",
                "signature": "signature_string"
            }
        }


class PaymentVerifyResponse(BaseModel):
    """Response schema for payment verification."""
    verified: bool = Field(..., description="Whether payment signature is valid")
    payment_id: str = Field(..., description="Razorpay payment ID")
    order_id: str = Field(..., description="Razorpay order ID")
    message: str = Field(..., description="Verification message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "verified": True,
                "payment_id": "pay_xyz789",
                "order_id": "order_abc123",
                "message": "Payment signature verified successfully"
            }
        }


# ============================================================================
# Webhook Schemas
# ============================================================================

class WebhookEvent(BaseModel):
    """Webhook event payload structure."""
    entity: str
    account_id: Optional[str] = None
    event: str
    contains: Optional[list] = None
    payload: Dict[str, Any]
    created_at: int


# ============================================================================
# Error Response Schema
# ============================================================================

class PaymentCaptureRequest(BaseModel):
    """Request schema for capturing a payment."""
    payment_id: str = Field(..., description="Razorpay payment ID")
    amount: Optional[float] = Field(None, description="Amount to capture in rupees (if None, captures full amount)")
    
    @validator("amount", pre=True)
    def validate_amount(cls, v):
        """Convert rupees to paise if provided."""
        if v is None:
            return None
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return int(v * 100)  # Convert to paise
    
    class Config:
        json_schema_extra = {
            "example": {
                "payment_id": "pay_xyz789",
                "amount": 100.0
            }
        }


class PaymentCaptureResponse(BaseModel):
    """Response schema for payment capture."""
    success: bool = Field(..., description="Whether capture was successful")
    payment_id: str = Field(..., description="Razorpay payment ID")
    status: str = Field(..., description="Payment status after capture")
    amount: int = Field(..., description="Captured amount in paise")
    message: str = Field(..., description="Capture message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "payment_id": "pay_xyz789",
                "status": "captured",
                "amount": 10000,
                "message": "Payment captured successfully"
            }
        }


# ============================================================================
# Subscription Schemas
# ============================================================================

class PlanItem(BaseModel):
    """Plan item schema."""
    name: str = Field(..., description="Item name")
    amount: float = Field(..., gt=0, description="Amount in rupees")
    currency: str = Field(default="INR", description="Currency code")
    description: Optional[str] = Field(None, description="Item description")
    
    @validator("amount")
    def validate_amount(cls, v):
        """Convert rupees to paise."""
        return int(v * 100)


class PlanCreateRequest(BaseModel):
    """Request schema for creating a plan."""
    period: str = Field(..., description="Billing period: daily, weekly, monthly, yearly")
    interval: int = Field(..., gt=0, description="Billing interval (e.g., 1 for monthly, 2 for every 2 months)")
    item: PlanItem = Field(..., description="Plan item details")
    notes: Optional[Dict[str, Any]] = Field(None, description="Additional notes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "period": "monthly",
                "interval": 1,
                "item": {
                    "name": "Premium Plan",
                    "amount": 500.0,
                    "currency": "INR",
                    "description": "Monthly premium subscription"
                },
                "notes": {
                    "feature": "premium"
                }
            }
        }


class SubscriptionCreateRequest(BaseModel):
    """Request schema for creating a subscription."""
    plan_id: str = Field(..., description="Razorpay plan ID")
    customer_notify: int = Field(default=1, description="Send notification to customer (1 = yes, 0 = no)")
    quantity: int = Field(default=1, gt=0, description="Number of subscriptions")
    start_at: Optional[int] = Field(None, description="Unix timestamp for subscription start (None = immediate)")
    total_count: Optional[int] = Field(None, description="Total billing cycles (None = infinite)")
    notes: Optional[Dict[str, Any]] = Field(None, description="Additional notes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "plan_abc123",
                "customer_notify": 1,
                "quantity": 1,
                "start_at": None,
                "total_count": 12,
                "notes": {
                    "customer_id": "cust_123"
                }
            }
        }


class SubscriptionCancelRequest(BaseModel):
    """Request schema for cancelling a subscription."""
    cancel_at_cycle_end: bool = Field(default=False, description="Cancel at end of current cycle")
    
    class Config:
        json_schema_extra = {
            "example": {
                "cancel_at_cycle_end": False
            }
        }


class SubscriptionPauseRequest(BaseModel):
    """Request schema for pausing a subscription."""
    pause_at: str = Field(default="immediate", description="When to pause: immediate or cycle_end")
    
    class Config:
        json_schema_extra = {
            "example": {
                "pause_at": "immediate"
            }
        }


class SubscriptionResumeRequest(BaseModel):
    """Request schema for resuming a subscription."""
    resume_at: str = Field(default="immediate", description="When to resume: immediate or cycle_end")
    
    class Config:
        json_schema_extra = {
            "example": {
                "resume_at": "immediate"
            }
        }


class SubscriptionResponse(BaseModel):
    """Response schema for subscription operations."""
    id: str = Field(..., description="Subscription ID")
    entity: str
    plan_id: str
    customer_id: Optional[str] = None
    status: str
    current_start: Optional[int] = None
    current_end: Optional[int] = None
    ended_at: Optional[int] = None
    quantity: int
    notes: Optional[Dict[str, Any]] = None
    charge_at: Optional[int] = None
    start_at: Optional[int] = None
    end_at: Optional[int] = None
    auth_attempts: int
    total_count: Optional[int] = None
    paid_count: int
    created_at: int
    
    @validator("notes", pre=True)
    def validate_notes(cls, v):
        """Handle notes as empty list or dict."""
        if v is None or v == []:
            return None
        if isinstance(v, dict):
            return v
        return None


class PlanResponse(BaseModel):
    """Response schema for plan operations."""
    id: str = Field(..., description="Plan ID")
    entity: str
    interval: int
    period: str
    item: Dict[str, Any]
    notes: Optional[Dict[str, Any]] = None
    created_at: int
    
    @validator("notes", pre=True)
    def validate_notes(cls, v):
        """Handle notes as empty list or dict."""
        if v is None or v == []:
            return None
        if isinstance(v, dict):
            return v
        return None


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Payment verification failed",
                "detail": "Invalid signature"
            }
        }
