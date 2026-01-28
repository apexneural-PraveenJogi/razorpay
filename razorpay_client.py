"""
Razorpay client initialization and utilities.
"""
from typing import Dict, Any, Optional

import razorpay
import requests
from requests.auth import HTTPBasicAuth

from config import settings


# Initialize Razorpay SDK client (used for utilities like signature verification,
# fetching payments/orders, etc.)
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_order(
    amount: int,
    currency: str = "INR",
    receipt: Optional[str] = None,
    notes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a Razorpay order (direct HTTP with explicit timeout).

    We use `requests` directly here so that:
    - Network / auth errors fail fast with clear messages
    - We can control timeouts explicitly (no hanging requests)
    - The rest of the codebase stays the same.

    Args:
        amount: Amount in paise (smallest currency unit)
        currency: Currency code (default: INR)
        receipt: Optional receipt identifier
        notes: Optional additional notes/metadata

    Returns:
        Parsed JSON order response from Razorpay API.

    Raises:
        requests.HTTPError or requests.RequestException on failure.
    """
    order_data: Dict[str, Any] = {
        "amount": amount,
        "currency": currency,
    }

    if receipt:
        order_data["receipt"] = receipt

    if notes:
        order_data["notes"] = notes

    response = requests.post(
        "https://api.razorpay.com/v1/orders",
        json=order_data,
        auth=HTTPBasicAuth(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
        timeout=10,  # seconds: (connect + read)
    )
    response.raise_for_status()
    return response.json()


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Verify payment signature.
    
    Args:
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        signature: Payment signature to verify
    
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        params = {
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature
        }
        client.utility.verify_payment_signature(params)
        return True
    except razorpay.errors.SignatureVerificationError:
        return False


def verify_webhook_signature(payload: str, signature: str) -> bool:
    """
    Verify webhook signature.
    
    Args:
        payload: Raw webhook payload (string)
        signature: Webhook signature from X-Razorpay-Signature header
    
    Returns:
        True if signature is valid, False otherwise
    """
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return False
    
    try:
        client.utility.verify_webhook_signature(payload, signature, settings.RAZORPAY_WEBHOOK_SECRET)
        return True
    except razorpay.errors.SignatureVerificationError:
        return False


def get_payment(payment_id: str) -> Dict[str, Any]:
    """
    Fetch payment details from Razorpay.
    
    Args:
        payment_id: Razorpay payment ID
    
    Returns:
        Payment details from Razorpay API
    """
    return client.payment.fetch(payment_id)


def get_order(order_id: str) -> Dict[str, Any]:
    """
    Fetch order details from Razorpay.
    
    Args:
        order_id: Razorpay order ID
    
    Returns:
        Order details from Razorpay API
    """
    return client.order.fetch(order_id)


def capture_payment(payment_id: str, amount: int = None) -> Dict[str, Any]:
    """
    Capture a payment that is in authorized state.
    
    Args:
        payment_id: Razorpay payment ID
        amount: Amount to capture in paise (if None, captures full amount)
    
    Returns:
        Captured payment response from Razorpay API
    """
    capture_data = {}
    if amount:
        capture_data["amount"] = amount
    
    return client.payment.capture(payment_id, capture_data)


# ============================================================================
# Subscription Methods
# ============================================================================

def create_subscription(plan_id: str, customer_notify: int = 1, quantity: int = 1, 
                       start_at: int = None, total_count: int = None, 
                       notes: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Create a Razorpay subscription.
    
    Args:
        plan_id: Razorpay plan ID
        customer_notify: Send notification to customer (1 = yes, 0 = no)
        quantity: Number of subscriptions
        start_at: Unix timestamp for subscription start (None = immediate)
        total_count: Total billing cycles (None = infinite)
        notes: Additional notes/metadata
    
    Returns:
        Subscription response from Razorpay API
    """
    subscription_data = {
        "plan_id": plan_id,
        "customer_notify": customer_notify,
        "quantity": quantity
    }
    
    if start_at:
        subscription_data["start_at"] = start_at
    
    if total_count:
        subscription_data["total_count"] = total_count
    
    if notes:
        subscription_data["notes"] = notes
    
    return client.subscription.create(data=subscription_data)


def get_subscription(subscription_id: str) -> Dict[str, Any]:
    """
    Fetch subscription details from Razorpay.
    
    Args:
        subscription_id: Razorpay subscription ID
    
    Returns:
        Subscription details from Razorpay API
    """
    return client.subscription.fetch(subscription_id)


def list_subscriptions(count: int = 10, skip: int = 0, plan_id: str = None, 
                      customer_id: str = None) -> Dict[str, Any]:
    """
    List subscriptions from Razorpay.
    
    Args:
        count: Number of subscriptions to fetch
        skip: Number of subscriptions to skip
        plan_id: Filter by plan ID
        customer_id: Filter by customer ID
    
    Returns:
        List of subscriptions from Razorpay API
    """
    params = {
        "count": count,
        "skip": skip
    }
    
    if plan_id:
        params["plan_id"] = plan_id
    
    if customer_id:
        params["customer_id"] = customer_id
    
    return client.subscription.all(params)


def cancel_subscription(subscription_id: str, cancel_at_cycle_end: bool = False) -> Dict[str, Any]:
    """
    Cancel a subscription.
    
    Args:
        subscription_id: Razorpay subscription ID
        cancel_at_cycle_end: Cancel at end of current cycle (True) or immediately (False)
    
    Returns:
        Cancelled subscription response from Razorpay API
    """
    data = {}
    if cancel_at_cycle_end:
        data["cancel_at_cycle_end"] = 1
    else:
        data["cancel_at_cycle_end"] = 0
    
    return client.subscription.cancel(subscription_id, data)


def pause_subscription(subscription_id: str, pause_at: str = "immediate") -> Dict[str, Any]:
    """
    Pause a subscription.
    
    Args:
        subscription_id: Razorpay subscription ID
        pause_at: When to pause ("immediate" or "cycle_end")
    
    Returns:
        Paused subscription response from Razorpay API
    """
    data = {"pause_at": pause_at}
    return client.subscription.pause(subscription_id, data)


def resume_subscription(subscription_id: str, resume_at: str = "immediate") -> Dict[str, Any]:
    """
    Resume a paused subscription.
    
    Args:
        subscription_id: Razorpay subscription ID
        resume_at: When to resume ("immediate" or "cycle_end")
    
    Returns:
        Resumed subscription response from Razorpay API
    """
    data = {"resume_at": resume_at}
    return client.subscription.resume(subscription_id, data)


def get_subscription_invoices(subscription_id: str) -> Dict[str, Any]:
    """
    Get invoices for a subscription.
    
    Args:
        subscription_id: Razorpay subscription ID
    
    Returns:
        List of invoices for the subscription
    """
    return client.invoice.all({"subscription_id": subscription_id})


def get_invoice(invoice_id: str) -> Dict[str, Any]:
    """
    Get invoice details.
    
    Args:
        invoice_id: Razorpay invoice ID
    
    Returns:
        Invoice details from Razorpay API
    """
    return client.invoice.fetch(invoice_id)


# ============================================================================
# Plan Methods
# ============================================================================

def create_plan(period: str, interval: int, item: Dict[str, Any], 
                notes: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Create a Razorpay plan.
    
    Args:
        period: Billing period ("daily", "weekly", "monthly", "yearly")
        interval: Billing interval (e.g., 1 for monthly, 2 for every 2 months)
        item: Item details with name, amount, currency, description
        notes: Additional notes/metadata
    
    Returns:
        Plan response from Razorpay API
    """
    plan_data = {
        "period": period,
        "interval": interval,
        "item": item
    }
    
    if notes:
        plan_data["notes"] = notes
    
    return client.plan.create(data=plan_data)


def get_plan(plan_id: str) -> Dict[str, Any]:
    """
    Fetch plan details from Razorpay.
    
    Args:
        plan_id: Razorpay plan ID
    
    Returns:
        Plan details from Razorpay API
    """
    return client.plan.fetch(plan_id)


def list_plans(count: int = 10, skip: int = 0) -> Dict[str, Any]:
    """
    List plans from Razorpay.
    
    Args:
        count: Number of plans to fetch
        skip: Number of plans to skip
    
    Returns:
        List of plans from Razorpay API
    """
    return client.plan.all({"count": count, "skip": skip})
