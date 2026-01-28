"""
FastAPI application with Razorpay integration endpoints.
"""
from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
import json
import logging

from config import settings
from database import get_db, init_db
from schemas import (
    OrderCreateRequest,
    OrderCreateResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
    PaymentCaptureRequest,
    PaymentCaptureResponse,
    ErrorResponse,
    WebhookEvent
)
from razorpay_client import (
    create_order,
    verify_payment_signature,
    get_payment,
    get_order,
    capture_payment
)
from webhook import process_webhook_event
from subscriptions import router as subscriptions_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Production-ready Razorpay payment integration with FastAPI",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include subscription router
app.include_router(subscriptions_router)


# ============================================================================
# Startup Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed: {str(e)}. Continuing without database...")


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.APP_NAME}


@app.get("/health/db", tags=["Health"])
async def health_check_db(db: AsyncSession = Depends(get_db)):
    """Database health check endpoint."""
    try:
        from sqlalchemy import text
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {
            "status": "healthy",
            "database": "connected",
            "service": settings.APP_NAME
        }
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
                "service": settings.APP_NAME
            }
        )


# ============================================================================
# Order Creation Endpoint
# ============================================================================

@app.post(
    "/api/v1/orders",
    response_model=OrderCreateResponse,
    status_code=201,
    tags=["Orders"],
    summary="Create Razorpay Order",
    description="""
    Create a new payment order with Razorpay.
    
    **Amount**: Provide amount in rupees (will be converted to paise automatically)
    
    **Example cURL**:
    ```bash
    curl -X POST "http://localhost:8000/api/v1/orders" \\
         -H "Content-Type: application/json" \\
         -d '{
           "amount": 100.0,
           "currency": "INR",
           "receipt": "receipt_001",
           "notes": {
             "customer_name": "John Doe"
           }
         }'
    ```
    
    **Frontend Usage (JavaScript)**:
    ```javascript
    const response = await fetch('http://localhost:8000/api/v1/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        amount: 100.0,
        currency: 'INR',
        receipt: 'receipt_001'
      })
    });
    const order = await response.json();
    ```
    """
)
async def create_order_endpoint(
    order_data: OrderCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new Razorpay order.
    
    The amount in the request is in rupees and will be automatically
    converted to paise (multiplied by 100) before creating the order.
    """
    try:
        # Create order with Razorpay (amount already converted to paise in schema)
        razorpay_order = create_order(
            amount=order_data.amount,  # Already in paise
            currency=order_data.currency,
            receipt=order_data.receipt,
            notes=order_data.notes
        )
        
        # Store order in database
        try:
            from database import Order
            from datetime import datetime
            from sqlalchemy import select
            
            # Check if order already exists
            result = await db.execute(
                select(Order).where(Order.id == razorpay_order["id"])
            )
            existing_order = result.scalar_one_or_none()
            
            if existing_order:
                # Update existing order
                existing_order.amount = razorpay_order["amount"]
                existing_order.amount_paid = razorpay_order.get("amount_paid", 0)
                existing_order.amount_due = razorpay_order.get("amount_due", razorpay_order["amount"])
                existing_order.status = razorpay_order["status"]
                existing_order.attempts = razorpay_order.get("attempts", 0)
                existing_order.notes = razorpay_order.get("notes")
                existing_order.updated_at = datetime.utcnow()
            else:
                # Create new order
                db_order = Order(
                    id=razorpay_order["id"],
                    amount=razorpay_order["amount"],
                    amount_paid=razorpay_order.get("amount_paid", 0),
                    amount_due=razorpay_order.get("amount_due", razorpay_order["amount"]),
                    currency=razorpay_order["currency"],
                    receipt=razorpay_order.get("receipt"),
                    status=razorpay_order["status"],
                    attempts=razorpay_order.get("attempts", 0),
                    notes=razorpay_order.get("notes"),
                    created_at=datetime.utcnow()
                )
                db.add(db_order)
            
            await db.commit()
            logger.info(f"Order {razorpay_order['id']} saved to database successfully")
        except Exception as db_error:
            logger.error(f"Failed to save order to database: {str(db_error)}", exc_info=True)
            await db.rollback()
            # Continue without database - order is still created in Razorpay
            # But log the error for debugging
        
        return OrderCreateResponse(**razorpay_order)
    
    except Exception as e:
        logger.error(f"Error creating order: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create order: {str(e)}"
        )


# ============================================================================
# Payment Verification Endpoint
# ============================================================================

@app.post(
    "/api/v1/payments/verify",
    response_model=PaymentVerifyResponse,
    tags=["Payments"],
    summary="Verify Payment Signature",
    description="""
    Verify the payment signature after successful payment.
    
    **Example cURL**:
    ```bash
    curl -X POST "http://localhost:8000/api/v1/payments/verify" \\
         -H "Content-Type: application/json" \\
         -d '{
           "order_id": "order_abc123",
           "payment_id": "pay_xyz789",
           "signature": "signature_string"
         }'
    ```
    
    **Frontend Usage (JavaScript)**:
    ```javascript
    const response = await fetch('http://localhost:8000/api/v1/payments/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        order_id: 'order_abc123',
        payment_id: 'pay_xyz789',
        signature: 'signature_from_razorpay'
      })
    });
    const verification = await response.json();
    ```
    """
)
async def verify_payment_endpoint(
    verification_data: PaymentVerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify payment signature after successful payment.
    
    This endpoint verifies that the payment was actually made through
    Razorpay and hasn't been tampered with.
    """
    try:
        # Verify signature
        is_verified = verify_payment_signature(
            order_id=verification_data.order_id,
            payment_id=verification_data.payment_id,
            signature=verification_data.signature
        )
        
        if not is_verified:
            return PaymentVerifyResponse(
                verified=False,
                payment_id=verification_data.payment_id,
                order_id=verification_data.order_id,
                message="Payment signature verification failed"
            )
        
        # Fetch payment details from Razorpay
        payment_details = get_payment(verification_data.payment_id)
        
        # Store/update payment in database (optional - continue even if DB fails)
        try:
            from database import Payment, PaymentStatus
            from sqlalchemy import select
            from datetime import datetime
            
            result = await db.execute(
                select(Payment).where(Payment.id == verification_data.payment_id)
            )
            existing_payment = result.scalar_one_or_none()
            
            # Use updated payment_status if payment was captured
            if payment_status == "captured":
                razorpay_status = "captured"
            else:
                razorpay_status = payment_details.get("status", "").lower()
            
            status_mapping = {
                "created": PaymentStatus.CREATED,
                "authorized": PaymentStatus.AUTHORIZED,
                "captured": PaymentStatus.CAPTURED,
                "refunded": PaymentStatus.REFUNDED,
                "failed": PaymentStatus.FAILED
            }
            payment_status = status_mapping.get(razorpay_status, PaymentStatus.FAILED)
            
            if not existing_payment:
                db_payment = Payment(
                    id=verification_data.payment_id,
                    order_id=verification_data.order_id,
                    amount=payment_details.get("amount", 0),
                    currency=payment_details.get("currency", "INR"),
                    status=payment_status,
                    method=payment_details.get("method"),
                    description=payment_details.get("description"),
                    razorpay_data=payment_details,
                    created_at=datetime.utcnow()
                )
                db.add(db_payment)
                await db.commit()
        except Exception as db_error:
            logger.warning(f"Failed to save payment to database: {str(db_error)}")
            # Continue without database - verification still works
        
        # Auto-capture payment if it's authorized
        payment_status = payment_details.get("status", "").lower()
        if payment_status == "authorized":
            try:
                logger.info(f"Auto-capturing authorized payment: {verification_data.payment_id}")
                captured_payment = capture_payment(verification_data.payment_id)
                logger.info(f"Payment {verification_data.payment_id} captured successfully")
                payment_details = captured_payment  # Update with captured payment details
                payment_status = "captured"  # Update status
            except Exception as capture_error:
                logger.warning(f"Failed to auto-capture payment: {str(capture_error)}")
                # Continue even if capture fails - payment is still verified
        
        return PaymentVerifyResponse(
            verified=True,
            payment_id=verification_data.payment_id,
            order_id=verification_data.order_id,
            message="Payment signature verified successfully"
        )
    
    except Exception as e:
        logger.error(f"Error verifying payment: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify payment: {str(e)}"
        )


# ============================================================================
# Payment Capture Endpoint
# ============================================================================

@app.post(
    "/api/v1/payments/capture",
    response_model=PaymentCaptureResponse,
    tags=["Payments"],
    summary="Capture Payment",
    description="""
    Capture an authorized payment.
    
    When a payment is made, it may be in "authorized" state. This endpoint
    captures the payment to complete the transaction.
    
    **Example cURL**:
    ```bash
    curl -X POST "http://localhost:8000/api/v1/payments/capture" \\
         -H "Content-Type: application/json" \\
         -d '{
           "payment_id": "pay_xyz789",
           "amount": 100.0
         }'
    ```
    
    **Note**: If amount is not provided, the full authorized amount will be captured.
    """
)
async def capture_payment_endpoint(
    capture_data: PaymentCaptureRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Capture an authorized payment.
    
    This endpoint captures a payment that is in "authorized" state,
    completing the transaction.
    """
    try:
        # Get current payment status
        payment_details = get_payment(capture_data.payment_id)
        current_status = payment_details.get("status", "").lower()
        
        if current_status == "captured":
            return PaymentCaptureResponse(
                success=True,
                payment_id=capture_data.payment_id,
                status="captured",
                amount=payment_details.get("amount", 0),
                message="Payment is already captured"
            )
        
        if current_status != "authorized":
            raise HTTPException(
                status_code=400,
                detail=f"Payment cannot be captured. Current status: {current_status}"
            )
        
        # Capture the payment
        captured_payment = capture_payment(
            payment_id=capture_data.payment_id,
            amount=capture_data.amount  # Already in paise from validator
        )
        
        # Update payment in database
        try:
            from database import Payment, PaymentStatus
            from sqlalchemy import select
            from datetime import datetime
            
            result = await db.execute(
                select(Payment).where(Payment.id == capture_data.payment_id)
            )
            existing_payment = result.scalar_one_or_none()
            
            if existing_payment:
                existing_payment.status = PaymentStatus.CAPTURED
                existing_payment.razorpay_data = captured_payment
                existing_payment.updated_at = datetime.utcnow()
            else:
                db_payment = Payment(
                    id=capture_data.payment_id,
                    order_id=captured_payment.get("order_id", ""),
                    amount=captured_payment.get("amount", 0),
                    currency=captured_payment.get("currency", "INR"),
                    status=PaymentStatus.CAPTURED,
                    method=captured_payment.get("method"),
                    description=captured_payment.get("description"),
                    razorpay_data=captured_payment,
                    created_at=datetime.utcnow()
                )
                db.add(db_payment)
            
            await db.commit()
            logger.info(f"Payment {capture_data.payment_id} captured and saved to database")
        except Exception as db_error:
            logger.warning(f"Failed to save captured payment to database: {str(db_error)}")
            await db.rollback()
        
        return PaymentCaptureResponse(
            success=True,
            payment_id=capture_data.payment_id,
            status=captured_payment.get("status", "captured"),
            amount=captured_payment.get("amount", 0),
            message="Payment captured successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error capturing payment: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to capture payment: {str(e)}"
        )


# ============================================================================
# Webhook Endpoint
# ============================================================================

@app.post(
    "/api/v1/webhooks/razorpay",
    tags=["Webhooks"],
    summary="Razorpay Webhook Handler",
    description="""
    Handle webhook events from Razorpay.
    
    This endpoint receives and processes webhook events from Razorpay,
    including payment status updates, order updates, etc.
    
    **Webhook Signature Verification**: Automatically verifies the webhook
    signature using RAZORPAY_WEBHOOK_SECRET from environment variables.
    
    **Example cURL** (for testing):
    ```bash
    curl -X POST "http://localhost:8000/api/v1/webhooks/razorpay" \\
         -H "Content-Type: application/json" \\
         -H "X-Razorpay-Signature: signature_string" \\
         -d '{
           "entity": "event",
           "account_id": "acc_xxx",
           "event": "payment.captured",
           "contains": ["payment"],
           "payload": {
             "payment": {
               "entity": {
                 "id": "pay_xxx",
                 "status": "captured"
               }
             }
           },
           "created_at": 1234567890
         }'
    ```
    
    **Note**: In production, Razorpay will send webhooks to this endpoint
    automatically when configured in the Razorpay dashboard.
    """
)
async def webhook_handler(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Razorpay webhook events.
    
    This endpoint processes webhook events from Razorpay and updates
    the database accordingly. Webhook signature is verified before processing.
    """
    try:
        # Get raw request body for signature verification
        body = await request.body()
        body_str = body.decode("utf-8")
        
        # Parse JSON payload
        event_data = json.loads(body_str)
        
        if not x_razorpay_signature:
            logger.warning("Webhook received without signature")
            raise HTTPException(
                status_code=400,
                detail="Missing X-Razorpay-Signature header"
            )
        
        # Process webhook event
        result = await process_webhook_event(
            event_data=event_data,
            signature=x_razorpay_signature,
            db=db
        )
        
        if result.get("success"):
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": result.get("message", "Webhook processed successfully")
                }
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": result.get("message", "Webhook processing failed")
                }
            )
    
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload"
        )
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process webhook: {str(e)}"
        )


# ============================================================================
# Additional Utility Endpoints
# ============================================================================

@app.get(
    "/api/v1/payments",
    tags=["Payments"],
    summary="List Payments from Database",
    description="Get all payments stored in the database."
)
async def list_payments_endpoint(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all payments from the database."""
    try:
        from database import Payment
        from sqlalchemy import select, desc
        
        result = await db.execute(
            select(Payment)
            .order_by(desc(Payment.created_at))
            .offset(skip)
            .limit(limit)
        )
        payments = result.scalars().all()
        
        return {
            "total": len(payments),
            "payments": [
                {
                    "id": payment.id,
                    "order_id": payment.order_id,
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "status": payment.status.value if payment.status else None,
                    "method": payment.method,
                    "description": payment.description,
                    "created_at": payment.created_at.isoformat() if payment.created_at else None,
                    "updated_at": payment.updated_at.isoformat() if payment.updated_at else None
                }
                for payment in payments
            ]
        }
    except Exception as e:
        logger.error(f"Error listing payments: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list payments: {str(e)}"
        )


@app.get(
    "/api/v1/payments/{payment_id}",
    tags=["Payments"],
    summary="Get Payment Details",
    description="Fetch payment details from Razorpay by payment ID."
)
async def get_payment_endpoint(payment_id: str):
    """Get payment details from Razorpay."""
    try:
        payment = get_payment(payment_id)
        return payment
    except Exception as e:
        logger.error(f"Error fetching payment: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"Payment not found: {str(e)}"
        )


@app.get(
    "/api/v1/payments/{payment_id}/db",
    tags=["Payments"],
    summary="Get Payment from Database",
    description="Fetch payment details from local database by payment ID."
)
async def get_payment_from_db_endpoint(
    payment_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get payment details from database."""
    try:
        from database import Payment
        from sqlalchemy import select
        
        result = await db.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            raise HTTPException(
                status_code=404,
                detail=f"Payment {payment_id} not found in database"
            )
        
        return {
            "id": payment.id,
            "order_id": payment.order_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "status": payment.status.value if payment.status else None,
            "method": payment.method,
            "description": payment.description,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
            "updated_at": payment.updated_at.isoformat() if payment.updated_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching payment from database: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch payment: {str(e)}"
        )


@app.get(
    "/api/v1/orders",
    tags=["Orders"],
    summary="List Orders from Database",
    description="Get all orders stored in the database."
)
async def list_orders_endpoint(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all orders from the database."""
    try:
        from database import Order
        from sqlalchemy import select
        from sqlalchemy import desc
        
        result = await db.execute(
            select(Order)
            .order_by(desc(Order.created_at))
            .offset(skip)
            .limit(limit)
        )
        orders = result.scalars().all()
        
        return {
            "total": len(orders),
            "orders": [
                {
                    "id": order.id,
                    "amount": order.amount,
                    "amount_paid": order.amount_paid,
                    "amount_due": order.amount_due,
                    "currency": order.currency,
                    "receipt": order.receipt,
                    "status": order.status,
                    "attempts": order.attempts,
                    "notes": order.notes,
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "updated_at": order.updated_at.isoformat() if order.updated_at else None
                }
                for order in orders
            ]
        }
    except Exception as e:
        logger.error(f"Error listing orders: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list orders: {str(e)}"
        )


@app.get(
    "/api/v1/orders/{order_id}",
    tags=["Orders"],
    summary="Get Order Details",
    description="Fetch order details from Razorpay by order ID."
)
async def get_order_endpoint(order_id: str):
    """Get order details from Razorpay."""
    try:
        order = get_order(order_id)
        return order
    except Exception as e:
        logger.error(f"Error fetching order: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"Order not found: {str(e)}"
        )


@app.get(
    "/api/v1/orders/{order_id}/db",
    tags=["Orders"],
    summary="Get Order from Database",
    description="Fetch order details from local database by order ID."
)
async def get_order_from_db_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get order details from database."""
    try:
        from database import Order
        from sqlalchemy import select
        
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            raise HTTPException(
                status_code=404,
                detail=f"Order {order_id} not found in database"
            )
        
        return {
            "id": order.id,
            "amount": order.amount,
            "amount_paid": order.amount_paid,
            "amount_due": order.amount_due,
            "currency": order.currency,
            "receipt": order.receipt,
            "status": order.status,
            "attempts": order.attempts,
            "notes": order.notes,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order from database: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch order: {str(e)}"
        )


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            detail=None
        ).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler."""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc) if settings.DEBUG else None
        ).dict()
    )


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
