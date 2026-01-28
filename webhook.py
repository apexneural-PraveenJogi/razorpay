"""
Webhook handling utilities and business logic.
"""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import Payment, Order, WebhookEvent, PaymentStatus, Subscription, SubscriptionPayment, SubscriptionStatus
from razorpay_client import verify_webhook_signature, get_payment, get_order, capture_payment
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)


async def process_webhook_event(
    event_data: Dict[str, Any],
    signature: str,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Process webhook event and update database.
    
    Args:
        event_data: Webhook event payload
        signature: Webhook signature
        db: Database session
    
    Returns:
        Processing result
    """
    # Verify webhook signature
    import json
    payload_str = json.dumps(event_data, separators=(',', ':'))
    is_verified = verify_webhook_signature(payload_str, signature)
    
    # Store webhook event
    # Razorpay sends a unique `id` at the top-level for events (e.g. "evt_...").
    # Use that when present; otherwise fall back to a deterministic hash to avoid PK collisions.
    event_id = (
        event_data.get("id")
        or event_data.get("event_id")
        or event_data.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
        or event_data.get("payload", {}).get("order", {}).get("entity", {}).get("id")
    )
    if not event_id:
        event_id = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    webhook_event = WebhookEvent(
        id=event_id,
        entity=event_data.get("entity", ""),
        event=event_data.get("event", ""),
        account_id=event_data.get("account_id"),
        payload=event_data,
        signature_verified="true" if is_verified else "false",
        processed="false",
        created_at=datetime.utcnow()
    )
    
    # Idempotent insert: if we receive the same event twice, don't 500.
    try:
        db.add(webhook_event)
        await db.flush()
    except Exception:
        await db.rollback()
        # If already exists, continue processing/ack (Razorpay retries webhooks).
        existing = await db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
        if existing.scalar_one_or_none() is None:
            raise
    
    if not is_verified:
        return {
            "success": False,
            "message": "Webhook signature verification failed",
            "event_id": webhook_event.id
        }
    
    # Process based on event type
    event_type = event_data.get("event", "")
    payload = event_data.get("payload", {})
    
    if event_type.startswith("payment."):
        result = await process_payment_event(event_type, payload, db)
    elif event_type.startswith("order."):
        result = await process_order_event(event_type, payload, db)
    elif event_type.startswith("subscription."):
        result = await process_subscription_event(event_type, payload, db)
    elif event_type.startswith("invoice."):
        result = await process_invoice_event(event_type, payload, db)
    else:
        result = {
            "success": True,
            "message": f"Event type {event_type} acknowledged but not processed",
            "event_id": webhook_event.id
        }
    
    # Mark webhook as processed
    webhook_event.processed = "true"
    await db.commit()
    
    return result


async def process_payment_event(
    event_type: str,
    payload: Dict[str, Any],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Process payment-related webhook events.
    
    Args:
        event_type: Type of payment event
        payload: Event payload
        db: Database session
    
    Returns:
        Processing result
    """
    # Handle different payload structures
    payment_entity = payload.get("payment", {})
    if isinstance(payment_entity, dict):
        payment_data = payment_entity.get("entity", payment_entity)
    else:
        payment_data = {}
    
    payment_id = payment_data.get("id")
    
    if not payment_id:
        return {
            "success": False,
            "message": "Payment ID not found in payload"
        }
    
    # Check if payment exists in database
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    
    # Map Razorpay status to our enum
    razorpay_status = payment_data.get("status", "").lower()
    status_mapping = {
        "created": PaymentStatus.CREATED,
        "authorized": PaymentStatus.AUTHORIZED,
        "captured": PaymentStatus.CAPTURED,
        "refunded": PaymentStatus.REFUNDED,
        "failed": PaymentStatus.FAILED
    }
    payment_status = status_mapping.get(razorpay_status, PaymentStatus.FAILED)
    
    # Auto-capture if payment is authorized
    if razorpay_status == "authorized":
        try:
            logger.info(f"Auto-capturing authorized payment from webhook: {payment_id}")
            captured_payment = capture_payment(payment_id)
            logger.info(f"Payment {payment_id} captured successfully via webhook")
            # Update payment_data with captured payment details
            payment_data = captured_payment
            payment_status = PaymentStatus.CAPTURED
        except Exception as capture_error:
            logger.warning(f"Failed to auto-capture payment {payment_id}: {str(capture_error)}")
            # Continue with authorized status if capture fails
    
    order_id = payment_data.get("order_id", "")
    
    if payment:
        # Update existing payment
        payment.status = payment_status
        payment.amount = payment_data.get("amount", payment.amount)
        payment.currency = payment_data.get("currency", payment.currency)
        payment.method = payment_data.get("method", payment.method)
        payment.description = payment_data.get("description", payment.description)
        payment.razorpay_data = payment_data
        payment.updated_at = datetime.utcnow()
    else:
        # Create new payment record
        payment = Payment(
            id=payment_id,
            order_id=order_id,
            amount=payment_data.get("amount", 0),
            currency=payment_data.get("currency", "INR"),
            status=payment_status,
            method=payment_data.get("method"),
            description=payment_data.get("description"),
            razorpay_data=payment_data,
            created_at=datetime.utcnow()
        )
        db.add(payment)
    
    await db.flush()
    
    # Handle payment.failed - update order attempts
    if event_type == "payment.failed" and order_id:
        try:
            order_result = await db.execute(select(Order).where(Order.id == order_id))
            order = order_result.scalar_one_or_none()
            if order:
                order.attempts = (order.attempts or 0) + 1
                order.updated_at = datetime.utcnow()
                await db.flush()
                logger.info(f"Updated order {order_id} attempts to {order.attempts}")
        except Exception as e:
            logger.warning(f"Failed to update order attempts: {str(e)}")
    
    # Handle payment.captured - update order status to paid
    if event_type == "payment.captured" and order_id:
        try:
            order_result = await db.execute(select(Order).where(Order.id == order_id))
            order = order_result.scalar_one_or_none()
            if order:
                order.status = "paid"
                order.amount_paid = payment_data.get("amount", order.amount_paid)
                order.amount_due = order.amount - order.amount_paid
                order.updated_at = datetime.utcnow()
                await db.flush()
                logger.info(f"Updated order {order_id} status to paid")
        except Exception as e:
            logger.warning(f"Failed to update order status: {str(e)}")
    
    return {
        "success": True,
        "message": f"Payment event {event_type} processed successfully",
        "payment_id": payment_id,
        "status": payment_status.value,
        "order_id": order_id
    }


async def process_order_event(
    event_type: str,
    payload: Dict[str, Any],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Process order-related webhook events.
    
    Args:
        event_type: Type of order event
        payload: Event payload
        db: Database session
    
    Returns:
        Processing result
    """
    order_data = payload.get("order", {}).get("entity", {})
    order_id = order_data.get("id")
    
    if not order_id:
        return {
            "success": False,
            "message": "Order ID not found in payload"
        }
    
    # Check if order exists in database
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if order:
        # Update existing order with all fields
        order.amount = order_data.get("amount", order.amount)
        order.amount_paid = order_data.get("amount_paid", order.amount_paid)
        order.amount_due = order_data.get("amount_due", order.amount_due)
        order.status = order_data.get("status", order.status)
        order.attempts = order_data.get("attempts", order.attempts)
        order.currency = order_data.get("currency", order.currency)
        order.receipt = order_data.get("receipt", order.receipt)
        order.notes = order_data.get("notes", order.notes)
        order.updated_at = datetime.utcnow()
        logger.info(f"Updated order {order_id} - status: {order.status}, paid: {order.amount_paid}")
    else:
        # Create new order record
        order = Order(
            id=order_id,
            amount=order_data.get("amount", 0),
            amount_paid=order_data.get("amount_paid", 0),
            amount_due=order_data.get("amount_due", 0),
            currency=order_data.get("currency", "INR"),
            receipt=order_data.get("receipt"),
            status=order_data.get("status", "created"),
            attempts=order_data.get("attempts", 0),
            notes=order_data.get("notes"),
            created_at=datetime.utcnow()
        )
        db.add(order)
        logger.info(f"Created new order {order_id} from webhook")
    
    await db.flush()
    
    return {
        "success": True,
        "message": f"Order event {event_type} processed successfully",
        "order_id": order_id,
        "status": order.status
    }


async def process_subscription_event(
    event_type: str,
    payload: Dict[str, Any],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Process subscription-related webhook events.
    
    Args:
        event_type: Type of subscription event
        payload: Event payload
        db: Database session
    
    Returns:
        Processing result
    """
    subscription_entity = payload.get("subscription", {})
    if isinstance(subscription_entity, dict):
        subscription_data = subscription_entity.get("entity", subscription_entity)
    else:
        subscription_data = {}
    
    subscription_id = subscription_data.get("id")
    
    if not subscription_id:
        return {
            "success": False,
            "message": "Subscription ID not found in payload"
        }
    
    # Check if subscription exists in database
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    
    # Map Razorpay status to our enum
    razorpay_status = subscription_data.get("status", "").lower()
    status_mapping = {
        "created": SubscriptionStatus.CREATED,
        "authenticated": SubscriptionStatus.AUTHENTICATED,
        "active": SubscriptionStatus.ACTIVE,
        "pending": SubscriptionStatus.PENDING,
        "halted": SubscriptionStatus.HALTED,
        "cancelled": SubscriptionStatus.CANCELLED,
        "completed": SubscriptionStatus.COMPLETED,
        "expired": SubscriptionStatus.EXPIRED,
        "paused": SubscriptionStatus.PAUSED
    }
    subscription_status = status_mapping.get(razorpay_status, SubscriptionStatus.CREATED)
    
    # Special handling for subscription.charged event
    if event_type == "subscription.charged":
        # Update paid_count when subscription is charged
        if subscription:
            subscription.paid_count = (subscription.paid_count or 0) + 1
            logger.info(f"Subscription {subscription_id} charged - paid_count: {subscription.paid_count}")
        
        # Also handle invoice if present in payload
        invoice_entity = payload.get("invoice", {})
        if isinstance(invoice_entity, dict):
            invoice_data = invoice_entity.get("entity", invoice_entity)
            if invoice_data.get("id"):
                await process_invoice_event("invoice.paid", {"invoice": {"entity": invoice_data}}, db)
    
    # Special handling for subscription.activated event
    if event_type == "subscription.activated":
        logger.info(f"Subscription {subscription_id} activated")
        # Subscription becomes active - ensure status is updated
    
    if subscription:
        # Update existing subscription with all fields
        subscription.status = subscription_status
        subscription.plan_id = subscription_data.get("plan_id", subscription.plan_id)
        subscription.customer_id = subscription_data.get("customer_id", subscription.customer_id)
        
        # Update timestamps if provided
        if subscription_data.get("current_start"):
            subscription.current_start = datetime.fromtimestamp(subscription_data.get("current_start"))
        if subscription_data.get("current_end"):
            subscription.current_end = datetime.fromtimestamp(subscription_data.get("current_end"))
        if subscription_data.get("ended_at"):
            subscription.ended_at = datetime.fromtimestamp(subscription_data.get("ended_at"))
        if subscription_data.get("charge_at"):
            subscription.charge_at = datetime.fromtimestamp(subscription_data.get("charge_at"))
        if subscription_data.get("start_at"):
            subscription.start_at = datetime.fromtimestamp(subscription_data.get("start_at"))
        if subscription_data.get("end_at"):
            subscription.end_at = datetime.fromtimestamp(subscription_data.get("end_at"))
        
        # Update other fields
        subscription.quantity = subscription_data.get("quantity", subscription.quantity)
        subscription.auth_attempts = subscription_data.get("auth_attempts", subscription.auth_attempts)
        subscription.total_count = subscription_data.get("total_count", subscription.total_count)
        # paid_count is updated above for charged events, otherwise keep existing
        if subscription_data.get("paid_count") is not None:
            subscription.paid_count = subscription_data.get("paid_count")
        subscription.notes = subscription_data.get("notes", subscription.notes)
        subscription.razorpay_data = subscription_data
        subscription.updated_at = datetime.utcnow()
    else:
        # Create new subscription record
        subscription = Subscription(
            id=subscription_id,
            plan_id=subscription_data.get("plan_id"),
            customer_id=subscription_data.get("customer_id"),
            status=subscription_status,
            current_start=datetime.fromtimestamp(subscription_data.get("current_start", 0)) if subscription_data.get("current_start") else None,
            current_end=datetime.fromtimestamp(subscription_data.get("current_end", 0)) if subscription_data.get("current_end") else None,
            ended_at=datetime.fromtimestamp(subscription_data.get("ended_at", 0)) if subscription_data.get("ended_at") else None,
            quantity=subscription_data.get("quantity", 1),
            notes=subscription_data.get("notes"),
            charge_at=datetime.fromtimestamp(subscription_data.get("charge_at", 0)) if subscription_data.get("charge_at") else None,
            start_at=datetime.fromtimestamp(subscription_data.get("start_at", 0)) if subscription_data.get("start_at") else None,
            end_at=datetime.fromtimestamp(subscription_data.get("end_at", 0)) if subscription_data.get("end_at") else None,
            auth_attempts=subscription_data.get("auth_attempts", 0),
            total_count=subscription_data.get("total_count"),
            paid_count=subscription_data.get("paid_count", 0),
            razorpay_data=subscription_data,
            created_at=datetime.utcnow()
        )
        db.add(subscription)
        logger.info(f"Created new subscription {subscription_id} from webhook")
    
    await db.flush()
    
    return {
        "success": True,
        "message": f"Subscription event {event_type} processed successfully",
        "subscription_id": subscription_id,
        "status": subscription_status.value,
        "paid_count": subscription.paid_count
    }


async def process_invoice_event(
    event_type: str,
    payload: Dict[str, Any],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Process invoice-related webhook events.
    
    Args:
        event_type: Type of invoice event
        payload: Event payload
        db: Database session
    
    Returns:
        Processing result
    """
    invoice_entity = payload.get("invoice", {})
    if isinstance(invoice_entity, dict):
        invoice_data = invoice_entity.get("entity", invoice_entity)
    else:
        invoice_data = {}
    
    invoice_id = invoice_data.get("id")
    subscription_id = invoice_data.get("subscription_id")
    payment_id = invoice_data.get("payment_id")
    
    if not invoice_id:
        return {
            "success": False,
            "message": "Invoice ID not found in payload"
        }
    
    # Check if subscription payment exists in database
    result = await db.execute(
        select(SubscriptionPayment).where(SubscriptionPayment.id == invoice_id)
    )
    subscription_payment = result.scalar_one_or_none()
    
    if subscription_payment:
        # Update existing payment with all fields
        subscription_payment.status = invoice_data.get("status", subscription_payment.status)
        subscription_payment.amount = invoice_data.get("amount", subscription_payment.amount)
        subscription_payment.currency = invoice_data.get("currency", subscription_payment.currency)
        subscription_payment.payment_id = payment_id or subscription_payment.payment_id
        subscription_payment.description = invoice_data.get("description", subscription_payment.description)
        if invoice_data.get("billing_period_start"):
            subscription_payment.billing_period_start = datetime.fromtimestamp(invoice_data.get("billing_period_start"))
        if invoice_data.get("billing_period_end"):
            subscription_payment.billing_period_end = datetime.fromtimestamp(invoice_data.get("billing_period_end"))
        subscription_payment.razorpay_data = invoice_data
        subscription_payment.updated_at = datetime.utcnow()
        logger.info(f"Updated invoice {invoice_id} - status: {subscription_payment.status}")
    else:
        # Create new subscription payment record
        subscription_payment = SubscriptionPayment(
            id=invoice_id,
            subscription_id=subscription_id or "",
            invoice_id=invoice_id,
            payment_id=payment_id,
            amount=invoice_data.get("amount", 0),
            currency=invoice_data.get("currency", "INR"),
            status=invoice_data.get("status", "issued"),
            description=invoice_data.get("description"),
            billing_period_start=datetime.fromtimestamp(invoice_data.get("billing_period_start", 0)) if invoice_data.get("billing_period_start") else None,
            billing_period_end=datetime.fromtimestamp(invoice_data.get("billing_period_end", 0)) if invoice_data.get("billing_period_end") else None,
            razorpay_data=invoice_data,
            created_at=datetime.utcnow()
        )
        db.add(subscription_payment)
        logger.info(f"Created new invoice {invoice_id} for subscription {subscription_id}")
    
    await db.flush()
    
    # If invoice is paid, update subscription paid_count
    if event_type == "invoice.paid" and subscription_id:
        try:
            sub_result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
            sub = sub_result.scalar_one_or_none()
            if sub:
                sub.paid_count = (sub.paid_count or 0) + 1
                sub.updated_at = datetime.utcnow()
                await db.flush()
                logger.info(f"Updated subscription {subscription_id} paid_count to {sub.paid_count}")
        except Exception as e:
            logger.warning(f"Failed to update subscription paid_count: {str(e)}")
    
    return {
        "success": True,
        "message": f"Invoice event {event_type} processed successfully",
        "invoice_id": invoice_id,
        "subscription_id": subscription_id,
        "status": subscription_payment.status
    }
