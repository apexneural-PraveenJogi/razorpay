"""
Subscription endpoints and business logic.
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime
import logging

from database import get_db, Subscription, SubscriptionPayment, SubscriptionStatus
from schemas import (
    PlanCreateRequest,
    PlanResponse,
    SubscriptionCreateRequest,
    SubscriptionResponse,
    SubscriptionCancelRequest,
    SubscriptionPauseRequest,
    SubscriptionResumeRequest
)
from razorpay_client import (
    create_plan,
    get_plan,
    list_plans,
    create_subscription,
    get_subscription,
    list_subscriptions,
    cancel_subscription,
    pause_subscription,
    resume_subscription,
    get_subscription_invoices,
    get_invoice
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/subscriptions", tags=["Subscriptions"])


# ============================================================================
# Plan Endpoints
# ============================================================================

@router.post("/plans", response_model=PlanResponse, status_code=201)
async def create_plan_endpoint(
    plan_data: PlanCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a Razorpay plan.
    
    Plans define the billing frequency and amount for subscriptions.
    """
    try:
        # Convert item amount to paise
        item_data = plan_data.item.dict()
        item_data["amount"] = int(plan_data.item.amount)  # Already in paise from validator
        
        # Create plan with Razorpay
        razorpay_plan = create_plan(
            period=plan_data.period,
            interval=plan_data.interval,
            item=item_data,
            notes=plan_data.notes
        )
        
        return PlanResponse(**razorpay_plan)
    
    except Exception as e:
        logger.error(f"Error creating plan: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create plan: {str(e)}"
        )


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan_endpoint(plan_id: str):
    """Get plan details from Razorpay."""
    try:
        plan = get_plan(plan_id)
        return PlanResponse(**plan)
    except Exception as e:
        logger.error(f"Error fetching plan: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"Plan not found: {str(e)}"
        )


@router.get("/plans")
async def list_plans_endpoint(count: int = 10, skip: int = 0):
    """List all plans from Razorpay."""
    try:
        plans = list_plans(count=count, skip=skip)
        return plans
    except Exception as e:
        logger.error(f"Error listing plans: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list plans: {str(e)}"
        )


# ============================================================================
# Subscription Endpoints
# ============================================================================

@router.post("", response_model=SubscriptionResponse, status_code=201)
async def create_subscription_endpoint(
    subscription_data: SubscriptionCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a Razorpay subscription.
    
    This creates a subscription for a customer based on a plan.
    """
    try:
        # Create subscription with Razorpay
        razorpay_subscription = create_subscription(
            plan_id=subscription_data.plan_id,
            customer_notify=subscription_data.customer_notify,
            quantity=subscription_data.quantity,
            start_at=subscription_data.start_at,
            total_count=subscription_data.total_count,
            notes=subscription_data.notes
        )
        
        # Store subscription in database
        try:
            from database import SubscriptionStatus
            
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
            
            subscription_status = status_mapping.get(
                razorpay_subscription.get("status", "").lower(),
                SubscriptionStatus.CREATED
            )
            
            db_subscription = Subscription(
                id=razorpay_subscription["id"],
                plan_id=razorpay_subscription.get("plan_id"),
                customer_id=razorpay_subscription.get("customer_id"),
                status=subscription_status,
                current_start=datetime.fromtimestamp(razorpay_subscription.get("current_start", 0)) if razorpay_subscription.get("current_start") else None,
                current_end=datetime.fromtimestamp(razorpay_subscription.get("current_end", 0)) if razorpay_subscription.get("current_end") else None,
                ended_at=datetime.fromtimestamp(razorpay_subscription.get("ended_at", 0)) if razorpay_subscription.get("ended_at") else None,
                quantity=razorpay_subscription.get("quantity", 1),
                notes=razorpay_subscription.get("notes"),
                charge_at=datetime.fromtimestamp(razorpay_subscription.get("charge_at", 0)) if razorpay_subscription.get("charge_at") else None,
                start_at=datetime.fromtimestamp(razorpay_subscription.get("start_at", 0)) if razorpay_subscription.get("start_at") else None,
                end_at=datetime.fromtimestamp(razorpay_subscription.get("end_at", 0)) if razorpay_subscription.get("end_at") else None,
                auth_attempts=razorpay_subscription.get("auth_attempts", 0),
                total_count=razorpay_subscription.get("total_count"),
                paid_count=razorpay_subscription.get("paid_count", 0),
                razorpay_data=razorpay_subscription,
                created_at=datetime.utcnow()
            )
            db.add(db_subscription)
            await db.commit()
            logger.info(f"Subscription {razorpay_subscription['id']} saved to database")
        except Exception as db_error:
            logger.warning(f"Failed to save subscription to database: {str(db_error)}")
            await db.rollback()
        
        return SubscriptionResponse(**razorpay_subscription)
    
    except Exception as e:
        logger.error(f"Error creating subscription: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create subscription: {str(e)}"
        )


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription_endpoint(subscription_id: str):
    """Get subscription details from Razorpay."""
    try:
        subscription = get_subscription(subscription_id)
        return SubscriptionResponse(**subscription)
    except Exception as e:
        logger.error(f"Error fetching subscription: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"Subscription not found: {str(e)}"
        )


@router.get("")
async def list_subscriptions_endpoint(
    count: int = 10,
    skip: int = 0,
    plan_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List subscriptions from Razorpay and database."""
    try:
        # Get from Razorpay
        razorpay_subs = list_subscriptions(
            count=count,
            skip=skip,
            plan_id=plan_id,
            customer_id=customer_id
        )
        
        return razorpay_subs
    except Exception as e:
        logger.error(f"Error listing subscriptions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list subscriptions: {str(e)}"
        )


@router.get("/db/list")
async def list_subscriptions_from_db(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all subscriptions from database."""
    try:
        result = await db.execute(
            select(Subscription)
            .offset(skip)
            .limit(limit)
        )
        subscriptions = result.scalars().all()
        
        return {
            "total": len(subscriptions),
            "subscriptions": [
                {
                    "id": sub.id,
                    "plan_id": sub.plan_id,
                    "customer_id": sub.customer_id,
                    "status": sub.status.value if sub.status else None,
                    "quantity": sub.quantity,
                    "total_count": sub.total_count,
                    "paid_count": sub.paid_count,
                    "created_at": sub.created_at.isoformat() if sub.created_at else None,
                    "updated_at": sub.updated_at.isoformat() if sub.updated_at else None
                }
                for sub in subscriptions
            ]
        }
    except Exception as e:
        logger.error(f"Error listing subscriptions from database: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list subscriptions: {str(e)}"
        )


@router.post("/{subscription_id}/cancel", response_model=SubscriptionResponse)
async def cancel_subscription_endpoint(
    subscription_id: str,
    cancel_data: SubscriptionCancelRequest,
    db: AsyncSession = Depends(get_db)
):
    """Cancel a subscription."""
    try:
        cancelled_sub = cancel_subscription(
            subscription_id=subscription_id,
            cancel_at_cycle_end=cancel_data.cancel_at_cycle_end
        )
        
        # Update in database
        try:
            result = await db.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
            db_sub = result.scalar_one_or_none()
            if db_sub:
                from database import SubscriptionStatus
                db_sub.status = SubscriptionStatus.CANCELLED
                db_sub.razorpay_data = cancelled_sub
                db_sub.updated_at = datetime.utcnow()
                await db.commit()
        except Exception as db_error:
            logger.warning(f"Failed to update subscription in database: {str(db_error)}")
            await db.rollback()
        
        return SubscriptionResponse(**cancelled_sub)
    
    except Exception as e:
        logger.error(f"Error cancelling subscription: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel subscription: {str(e)}"
        )


@router.post("/{subscription_id}/pause", response_model=SubscriptionResponse)
async def pause_subscription_endpoint(
    subscription_id: str,
    pause_data: SubscriptionPauseRequest,
    db: AsyncSession = Depends(get_db)
):
    """Pause a subscription."""
    try:
        paused_sub = pause_subscription(
            subscription_id=subscription_id,
            pause_at=pause_data.pause_at
        )
        
        # Update in database
        try:
            result = await db.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
            db_sub = result.scalar_one_or_none()
            if db_sub:
                from database import SubscriptionStatus
                db_sub.status = SubscriptionStatus.PAUSED
                db_sub.razorpay_data = paused_sub
                db_sub.updated_at = datetime.utcnow()
                await db.commit()
        except Exception as db_error:
            logger.warning(f"Failed to update subscription in database: {str(db_error)}")
            await db.rollback()
        
        return SubscriptionResponse(**paused_sub)
    
    except Exception as e:
        logger.error(f"Error pausing subscription: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to pause subscription: {str(e)}"
        )


@router.post("/{subscription_id}/resume", response_model=SubscriptionResponse)
async def resume_subscription_endpoint(
    subscription_id: str,
    resume_data: SubscriptionResumeRequest,
    db: AsyncSession = Depends(get_db)
):
    """Resume a paused subscription."""
    try:
        resumed_sub = resume_subscription(
            subscription_id=subscription_id,
            resume_at=resume_data.resume_at
        )
        
        # Update in database
        try:
            result = await db.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
            db_sub = result.scalar_one_or_none()
            if db_sub:
                from database import SubscriptionStatus
                db_sub.status = SubscriptionStatus.ACTIVE
                db_sub.razorpay_data = resumed_sub
                db_sub.updated_at = datetime.utcnow()
                await db.commit()
        except Exception as db_error:
            logger.warning(f"Failed to update subscription in database: {str(db_error)}")
            await db.rollback()
        
        return SubscriptionResponse(**resumed_sub)
    
    except Exception as e:
        logger.error(f"Error resuming subscription: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resume subscription: {str(e)}"
        )


@router.get("/{subscription_id}/invoices")
async def get_subscription_invoices_endpoint(subscription_id: str):
    """Get invoices for a subscription."""
    try:
        invoices = get_subscription_invoices(subscription_id)
        return invoices
    except Exception as e:
        logger.error(f"Error fetching subscription invoices: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch invoices: {str(e)}"
        )


@router.get("/invoices/{invoice_id}")
async def get_invoice_endpoint(invoice_id: str):
    """Get invoice details."""
    try:
        invoice = get_invoice(invoice_id)
        return invoice
    except Exception as e:
        logger.error(f"Error fetching invoice: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"Invoice not found: {str(e)}"
        )
