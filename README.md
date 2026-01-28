# Razorpay FastAPI Integration

Production-ready Razorpay payment integration with FastAPI, PostgreSQL, and comprehensive subscription management.

## Quick Start

```bash
cd razorpay_fastapi

# Activate virtual environment
source ../venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your Razorpay credentials

# Initialize database
python3 setup_db.py

# Run server
uvicorn main:app --host 0.0.0.0 --port 8000
```

**API Documentation:**
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Environment Variables

Required in `.env`:
```env
RAZORPAY_KEY_ID=rzp_test_xxxxx
RAZORPAY_KEY_SECRET=your_secret_key
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/razorpay_db
DEBUG=true
```

---

## All API Endpoints

### Health Check Endpoints

#### `GET /health`
Check application health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "Razorpay FastAPI Integration"
}
```

**Usage:**
```bash
curl http://localhost:8000/health
```

---

#### `GET /health/db`
Check database connection status.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "service": "Razorpay FastAPI Integration"
}
```

**Usage:**
```bash
curl http://localhost:8000/health/db
```

---

## Order Management Endpoints

### `POST /api/v1/orders`
Create a new Razorpay order.

**Request Body:**
```json
{
  "amount": 100.0,
  "currency": "INR",
  "receipt": "receipt_001",
  "notes": {
    "customer_name": "John Doe",
    "order_id": "order_123"
  }
}
```

**Note:** Amount is in **rupees** - automatically converted to **paise** (multiplied by 100).

**Response:**
```json
{
  "id": "order_abc123",
  "entity": "order",
  "amount": 10000,
  "amount_paid": 0,
  "amount_due": 10000,
  "currency": "INR",
  "receipt": "receipt_001",
  "status": "created",
  "attempts": 0,
  "notes": {...},
  "created_at": 1234567890
}
```

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 100.0,
    "currency": "INR",
    "receipt": "receipt_001",
    "notes": {"purpose": "demo"}
  }'
```

**Frontend Usage:**
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

---

### `GET /api/v1/orders`
List all orders from database.

**Query Parameters:**
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 100) - Maximum number of records to return

**Response:**
```json
{
  "total": 10,
  "orders": [
    {
      "id": "order_abc123",
      "amount": 10000,
      "amount_paid": 0,
      "amount_due": 10000,
      "currency": "INR",
      "receipt": "receipt_001",
      "status": "created",
      "attempts": 0,
      "notes": {...},
      "created_at": "2026-01-28T10:00:00",
      "updated_at": "2026-01-28T10:00:00"
    }
  ]
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/orders?skip=0&limit=50"
```

---

### `GET /api/v1/orders/{order_id}`
Get order details from Razorpay.

**Path Parameters:**
- `order_id` (string, required) - Razorpay order ID

**Response:**
```json
{
  "id": "order_abc123",
  "entity": "order",
  "amount": 10000,
  "status": "created",
  ...
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/orders/order_abc123"
```

---

### `GET /api/v1/orders/{order_id}/db`
Get order details from local database.

**Path Parameters:**
- `order_id` (string, required) - Razorpay order ID

**Response:**
```json
{
  "id": "order_abc123",
  "amount": 10000,
  "status": "created",
  "created_at": "2026-01-28T10:00:00",
  ...
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/orders/order_abc123/db"
```

---

## Payment Management Endpoints

### `POST /api/v1/payments/verify`
Verify payment signature and auto-capture if authorized.

**Request Body:**
```json
{
  "order_id": "order_abc123",
  "payment_id": "pay_xyz789",
  "signature": "signature_from_razorpay"
}
```

**Response:**
```json
{
  "verified": true,
  "payment_id": "pay_xyz789",
  "order_id": "order_abc123",
  "message": "Payment signature verified successfully"
}
```

**Note:** Automatically captures payment if status is "authorized".

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/payments/verify" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "order_abc123",
    "payment_id": "pay_xyz789",
    "signature": "signature_from_razorpay"
  }'
```

**Frontend Usage:**
```javascript
// After Razorpay checkout success
const response = await fetch('http://localhost:8000/api/v1/payments/verify', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    order_id: razorpay_order_id,
    payment_id: razorpay_payment_id,
    signature: razorpay_signature
  })
});
const result = await response.json();
```

---

### `POST /api/v1/payments/capture`
Manually capture an authorized payment.

**Request Body:**
```json
{
  "payment_id": "pay_xyz789",
  "amount": 100.0
}
```

**Note:** If `amount` is not provided, full authorized amount is captured.

**Response:**
```json
{
  "success": true,
  "payment_id": "pay_xyz789",
  "status": "captured",
  "amount": 10000,
  "message": "Payment captured successfully"
}
```

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/payments/capture" \
  -H "Content-Type: application/json" \
  -d '{
    "payment_id": "pay_xyz789",
    "amount": 100.0
  }'
```

---

### `GET /api/v1/payments`
List all payments from database.

**Query Parameters:**
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 100) - Maximum number of records to return

**Response:**
```json
{
  "total": 5,
  "payments": [
    {
      "id": "pay_xyz789",
      "order_id": "order_abc123",
      "amount": 10000,
      "currency": "INR",
      "status": "captured",
      "method": "card",
      "created_at": "2026-01-28T10:00:00"
    }
  ]
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/payments?skip=0&limit=50"
```

---

### `GET /api/v1/payments/{payment_id}`
Get payment details from Razorpay.

**Path Parameters:**
- `payment_id` (string, required) - Razorpay payment ID

**Response:**
```json
{
  "id": "pay_xyz789",
  "entity": "payment",
  "amount": 10000,
  "status": "captured",
  ...
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/payments/pay_xyz789"
```

---

### `GET /api/v1/payments/{payment_id}/db`
Get payment details from local database.

**Path Parameters:**
- `payment_id` (string, required) - Razorpay payment ID

**Response:**
```json
{
  "id": "pay_xyz789",
  "order_id": "order_abc123",
  "amount": 10000,
  "status": "captured",
  "created_at": "2026-01-28T10:00:00"
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/payments/pay_xyz789/db"
```

---

## Webhook Endpoints

### `POST /api/v1/webhooks/razorpay`
Handle webhook events from Razorpay.

**Headers:**
- `X-Razorpay-Signature` (required) - Webhook signature for verification
- `Content-Type: application/json`

**Request Body:**
```json
{
  "id": "evt_abc123",
  "entity": "event",
  "event": "payment.captured",
  "account_id": "acc_xxx",
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_xxx",
        "status": "captured"
      }
    }
  },
  "created_at": 1234567890
}
```

**Supported Events:**
- `payment.captured` - Payment successfully captured
- `payment.authorized` - Payment authorized (auto-captured)
- `payment.failed` - Payment failed
- `order.paid` - Order payment completed
- `subscription.charged` - Subscription billing cycle charged
- `subscription.activated` - Subscription activated
- `subscription.cancelled` - Subscription cancelled
- `subscription.paused` - Subscription paused
- `subscription.resumed` - Subscription resumed
- `invoice.paid` - Invoice payment received
- `invoice.payment_failed` - Invoice payment failed

**Response:**
```json
{
  "success": true,
  "message": "Webhook processed successfully"
}
```

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/webhooks/razorpay" \
  -H "Content-Type: application/json" \
  -H "X-Razorpay-Signature: signature_from_razorpay" \
  -d '{
    "entity": "event",
    "event": "payment.captured",
    "payload": {...}
  }'
```

**Configuration:**
1. Go to Razorpay Dashboard → Settings → Webhooks
2. Add webhook URL: `https://yourdomain.com/api/v1/webhooks/razorpay`
3. Select events to receive
4. Copy webhook secret to `.env` as `RAZORPAY_WEBHOOK_SECRET`

---

### `GET /api/v1/webhooks/events`
List all webhook events received.

**Query Parameters:**
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 100) - Maximum number of records to return
- `event_type` (string, optional) - Filter by event type (e.g., "payment.captured")

**Response:**
```json
{
  "total": 10,
  "events": [
    {
      "id": "evt_abc123",
      "entity": "event",
      "event": "payment.captured",
      "account_id": "acc_xxx",
      "signature_verified": "true",
      "processed": "true",
      "created_at": "2026-01-28T10:00:00"
    }
  ]
}
```

**Usage:**
```bash
# List all events
curl "http://localhost:8000/api/v1/webhooks/events"

# Filter by event type
curl "http://localhost:8000/api/v1/webhooks/events?event_type=payment.captured"
```

---

## Plan Management Endpoints

### `POST /api/v1/subscriptions/plans`
Create a new subscription plan.

**Request Body:**
```json
{
  "period": "monthly",
  "interval": 1,
  "item": {
    "name": "Premium Plan",
    "amount": 500.0,
    "currency": "INR",
    "description": "Monthly premium subscription"
  },
  "notes": {
    "tier": "premium"
  }
}
```

**Period Options:** `daily`, `weekly`, `monthly`, `yearly`

**Response:**
```json
{
  "id": "plan_abc123",
  "entity": "plan",
  "interval": 1,
  "period": "monthly",
  "item": {...},
  "created_at": 1234567890
}
```

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/subscriptions/plans" \
  -H "Content-Type: application/json" \
  -d '{
    "period": "monthly",
    "interval": 1,
    "item": {
      "name": "Premium Plan",
      "amount": 500.0,
      "currency": "INR",
      "description": "Monthly premium subscription"
    }
  }'
```

---

### `GET /api/v1/subscriptions/plans`
List all plans from Razorpay.

**Query Parameters:**
- `count` (int, default: 10) - Number of plans to fetch
- `skip` (int, default: 0) - Number of plans to skip

**Response:**
```json
{
  "entity": "collection",
  "count": 5,
  "items": [
    {
      "id": "plan_abc123",
      "period": "monthly",
      "item": {...}
    }
  ]
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/subscriptions/plans?count=10&skip=0"
```

---

### `GET /api/v1/subscriptions/plans/{plan_id}`
Get plan details from Razorpay.

**Path Parameters:**
- `plan_id` (string, required) - Razorpay plan ID

**Response:**
```json
{
  "id": "plan_abc123",
  "entity": "plan",
  "period": "monthly",
  "item": {...}
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/subscriptions/plans/plan_abc123"
```

---

## Subscription Management Endpoints

### `POST /api/v1/subscriptions`
Create a new subscription.

**Request Body:**
```json
{
  "plan_id": "plan_abc123",
  "customer_notify": 1,
  "quantity": 1,
  "start_at": null,
  "total_count": 12,
  "notes": {
    "customer_id": "cust_123"
  }
}
```

**Parameters:**
- `plan_id` (required) - Razorpay plan ID
- `customer_notify` (int, default: 1) - Send notification to customer (1 = yes, 0 = no)
- `quantity` (int, default: 1) - Number of subscriptions
- `start_at` (int, optional) - Unix timestamp for subscription start (null = immediate)
- `total_count` (int, optional) - Total billing cycles (null = infinite)
- `notes` (object, optional) - Additional metadata

**Response:**
```json
{
  "id": "sub_xyz789",
  "entity": "subscription",
  "plan_id": "plan_abc123",
  "status": "created",
  "quantity": 1,
  "total_count": 12,
  "paid_count": 0,
  "created_at": 1234567890
}
```

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "plan_abc123",
    "customer_notify": 1,
    "quantity": 1,
    "total_count": 12
  }'
```

---

### `GET /api/v1/subscriptions`
List all subscriptions from Razorpay.

**Query Parameters:**
- `count` (int, default: 10) - Number of subscriptions to fetch
- `skip` (int, default: 0) - Number of subscriptions to skip
- `plan_id` (string, optional) - Filter by plan ID
- `customer_id` (string, optional) - Filter by customer ID

**Response:**
```json
{
  "entity": "collection",
  "count": 5,
  "items": [
    {
      "id": "sub_xyz789",
      "plan_id": "plan_abc123",
      "status": "active",
      "paid_count": 3,
      ...
    }
  ]
}
```

**Usage:**
```bash
# List all
curl "http://localhost:8000/api/v1/subscriptions?count=10"

# Filter by plan
curl "http://localhost:8000/api/v1/subscriptions?plan_id=plan_abc123"
```

---

### `GET /api/v1/subscriptions/db/list`
List all subscriptions from local database.

**Query Parameters:**
- `skip` (int, default: 0) - Number of records to skip
- `limit` (int, default: 100) - Maximum number of records to return

**Response:**
```json
{
  "total": 5,
  "subscriptions": [
    {
      "id": "sub_xyz789",
      "plan_id": "plan_abc123",
      "status": "active",
      "paid_count": 3,
      "created_at": "2026-01-28T10:00:00"
    }
  ]
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/subscriptions/db/list?skip=0&limit=100"
```

---

### `GET /api/v1/subscriptions/{subscription_id}`
Get subscription details from Razorpay.

**Path Parameters:**
- `subscription_id` (string, required) - Razorpay subscription ID

**Response:**
```json
{
  "id": "sub_xyz789",
  "entity": "subscription",
  "plan_id": "plan_abc123",
  "status": "active",
  "paid_count": 3,
  ...
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/subscriptions/sub_xyz789"
```

---

### `POST /api/v1/subscriptions/{subscription_id}/pause`
Pause a subscription.

**Request Body:**
```json
{
  "pause_at": "immediate"
}
```

**Options:**
- `"immediate"` - Pause immediately
- `"cycle_end"` - Pause at end of current billing cycle

**Response:**
```json
{
  "id": "sub_xyz789",
  "status": "paused",
  ...
}
```

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/subscriptions/sub_xyz789/pause" \
  -H "Content-Type: application/json" \
  -d '{"pause_at":"immediate"}'
```

---

### `POST /api/v1/subscriptions/{subscription_id}/resume`
Resume a paused subscription.

**Request Body:**
```json
{
  "resume_at": "immediate"
}
```

**Options:**
- `"immediate"` - Resume immediately
- `"cycle_end"` - Resume at end of current billing cycle

**Response:**
```json
{
  "id": "sub_xyz789",
  "status": "active",
  ...
}
```

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/subscriptions/sub_xyz789/resume" \
  -H "Content-Type: application/json" \
  -d '{"resume_at":"immediate"}'
```

---

### `POST /api/v1/subscriptions/{subscription_id}/cancel`
Cancel a subscription.

**Request Body:**
```json
{
  "cancel_at_cycle_end": false
}
```

**Options:**
- `false` - Cancel immediately
- `true` - Cancel at end of current billing cycle

**Response:**
```json
{
  "id": "sub_xyz789",
  "status": "cancelled",
  ...
}
```

**Usage:**
```bash
# Cancel immediately
curl -X POST "http://localhost:8000/api/v1/subscriptions/sub_xyz789/cancel" \
  -H "Content-Type: application/json" \
  -d '{"cancel_at_cycle_end":false}'

# Cancel at cycle end
curl -X POST "http://localhost:8000/api/v1/subscriptions/sub_xyz789/cancel" \
  -H "Content-Type: application/json" \
  -d '{"cancel_at_cycle_end":true}'
```

---

## Invoice Management Endpoints

### `GET /api/v1/subscriptions/{subscription_id}/invoices`
Get all invoices for a subscription.

**Path Parameters:**
- `subscription_id` (string, required) - Razorpay subscription ID

**Response:**
```json
{
  "entity": "collection",
  "count": 3,
  "items": [
    {
      "id": "inv_abc123",
      "entity": "invoice",
      "amount": 50000,
      "status": "paid",
      "subscription_id": "sub_xyz789",
      ...
    }
  ]
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/subscriptions/sub_xyz789/invoices"
```

---

### `GET /api/v1/subscriptions/invoices/{invoice_id}`
Get invoice details.

**Path Parameters:**
- `invoice_id` (string, required) - Razorpay invoice ID

**Response:**
```json
{
  "id": "inv_abc123",
  "entity": "invoice",
  "amount": 50000,
  "status": "paid",
  "subscription_id": "sub_xyz789",
  ...
}
```

**Usage:**
```bash
curl "http://localhost:8000/api/v1/subscriptions/invoices/inv_abc123"
```

---

## Complete Payment Flow Example

### Step 1: Create Order
```bash
ORDER_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/orders" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100.0, "currency": "INR", "receipt": "test_001"}')

ORDER_ID=$(echo $ORDER_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Order ID: $ORDER_ID"
```

### Step 2: Customer Pays (Frontend)
```javascript
// Integrate Razorpay Checkout
const options = {
  "key": "rzp_test_xxxxx",
  "amount": 10000, // Amount in paise
  "currency": "INR",
  "name": "Your Company",
  "description": "Test Transaction",
  "order_id": orderId, // From Step 1
  "handler": function (response) {
    // Step 3: Verify payment
    verifyPayment(response);
  }
};

const rzp = new Razorpay(options);
rzp.open();
```

### Step 3: Verify Payment
```javascript
async function verifyPayment(response) {
  const result = await fetch('http://localhost:8000/api/v1/payments/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      order_id: response.razorpay_order_id,
      payment_id: response.razorpay_payment_id,
      signature: response.razorpay_signature
    })
  });
  
  const data = await result.json();
  if (data.verified) {
    console.log('Payment verified and captured!');
  }
}
```

---

## Complete Subscription Flow Example

### Step 1: Create Plan
```bash
PLAN_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/subscriptions/plans" \
  -H "Content-Type: application/json" \
  -d '{
    "period": "monthly",
    "interval": 1,
    "item": {
      "name": "Basic Plan",
      "amount": 299.0,
      "currency": "INR"
    }
  }')

PLAN_ID=$(echo $PLAN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Plan ID: $PLAN_ID"
```

### Step 2: Create Subscription
```bash
SUB_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/subscriptions" \
  -H "Content-Type: application/json" \
  -d "{
    \"plan_id\": \"$PLAN_ID\",
    \"total_count\": 12
  }")

SUB_ID=$(echo $SUB_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Subscription ID: $SUB_ID"
```

### Step 3: Customer Authenticates Payment
Customer needs to authenticate payment method via Razorpay checkout (subscription will have `short_url` in response).

### Step 4: Subscription Becomes Active
Once authenticated, subscription status changes to "active" and automatic billing begins.

### Step 5: Manage Subscription
```bash
# Pause subscription
curl -X POST "http://localhost:8000/api/v1/subscriptions/$SUB_ID/pause" \
  -H "Content-Type: application/json" \
  -d '{"pause_at":"immediate"}'

# Resume subscription
curl -X POST "http://localhost:8000/api/v1/subscriptions/$SUB_ID/resume" \
  -H "Content-Type: application/json" \
  -d '{"resume_at":"immediate"}'

# Cancel subscription
curl -X POST "http://localhost:8000/api/v1/subscriptions/$SUB_ID/cancel" \
  -H "Content-Type: application/json" \
  -d '{"cancel_at_cycle_end":false}'
```

---

## Frontend HTML Files

Simple HTML frontends are included for testing:

- `subscription_frontend.html` - Complete subscription management UI
- `complete_payment.html` - Order creation + payment flow
- `test_payment_capture.html` - Payment testing page
- `test_50_rupees.html` - Quick payment test

**Serve them:**
```bash
cd razorpay_fastapi
python3 -m http.server 8080
```

**Access:**
- `http://localhost:8080/subscription_frontend.html`
- `http://localhost:8080/complete_payment.html`

---

## Database Setup

### Initialize Database
```bash
python3 setup_db.py
```

### Database Tables
- `orders` - Order records
- `payments` - Payment records
- `subscriptions` - Subscription records
- `subscription_payments` - Invoice/payment records
- `webhook_events` - Webhook event logs

### Direct Database Queries
```bash
# View orders
PGPASSWORD=postgres psql -h localhost -U postgres -d razorpay_db \
  -c "SELECT id, amount, status, created_at FROM orders ORDER BY created_at DESC;"

# View payments
PGPASSWORD=postgres psql -h localhost -U postgres -d razorpay_db \
  -c "SELECT id, order_id, amount, status FROM payments ORDER BY created_at DESC;"

# View subscriptions
PGPASSWORD=postgres psql -h localhost -U postgres -d razorpay_db \
  -c "SELECT id, plan_id, status, paid_count FROM subscriptions;"
```

---

## Webhook Configuration

### Setup Webhook in Razorpay Dashboard

1. **Go to:** Razorpay Dashboard → Settings → Webhooks
2. **Add Webhook URL:** `https://yourdomain.com/api/v1/webhooks/razorpay`
3. **Select Events:**
   - `payment.captured`
   - `payment.authorized`
   - `payment.failed`
   - `order.paid`
   - `subscription.charged`
   - `subscription.activated`
   - `subscription.cancelled`
   - `invoice.paid`
   - `invoice.payment_failed`
4. **Copy Webhook Secret** to `.env` as `RAZORPAY_WEBHOOK_SECRET`

### For Local Testing

Use **ngrok** to expose localhost:
```bash
# Install ngrok
# Run:
ngrok http 8000

# Use the ngrok URL as webhook URL:
# https://abc123.ngrok.io/api/v1/webhooks/razorpay
```

---

## Features

✅ **Order Management** - Create, list, and retrieve orders  
✅ **Payment Processing** - Verify, capture, and track payments  
✅ **Auto-Capture** - Automatically captures authorized payments  
✅ **Subscription Management** - Complete subscription lifecycle  
✅ **Plan Management** - Create and manage subscription plans  
✅ **Webhook Handling** - Process all Razorpay webhook events  
✅ **Database Persistence** - PostgreSQL storage for all entities  
✅ **Error Handling** - Comprehensive error handling and logging  
✅ **Signature Verification** - Secure payment and webhook verification  

---

## Amount Handling

**Important:** All amounts in API requests are in **rupees** (e.g., 100.0), but Razorpay stores them in **paise** (smallest currency unit). The system automatically converts:
- **Input:** 100.0 rupees → **Stored:** 10000 paise
- **Output:** 10000 paise → **Displayed:** 100.0 rupees (if needed)

---

## Error Responses

All endpoints return standard error format:
```json
{
  "error": "Error message",
  "detail": "Detailed error information (if DEBUG=true)"
}
```

---

## Testing

### Test Cards (Test Mode)
- **Card Number:** `4111 1111 1111 1111`
- **Expiry:** Any future date
- **CVV:** Any 3 digits
- **Name:** Any name

### Test Endpoints
```bash
# Health check
curl http://localhost:8000/health

# Create test order
curl -X POST "http://localhost:8000/api/v1/orders" \
  -H "Content-Type: application/json" \
  -d '{"amount": 50.0, "currency": "INR"}'
```

---

## Project Structure

```
razorpay_fastapi/
├── main.py                 # FastAPI application & endpoints
├── config.py              # Environment configuration
├── database.py            # Database models & setup
├── razorpay_client.py     # Razorpay SDK client
├── schemas.py             # Pydantic request/response models
├── webhook.py             # Webhook event processing
├── subscriptions.py       # Subscription endpoints
├── setup_db.py            # Database initialization script
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variables template
└── *.html                 # Frontend test pages
```

---

## Support

For issues or questions:
- Check API documentation: `http://localhost:8000/docs`
- Review logs for detailed error messages
- Verify environment variables in `.env`
- Check database connection: `GET /health/db`
