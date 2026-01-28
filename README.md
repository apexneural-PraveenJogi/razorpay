# Razorpay FastAPI (Orders + Payments + Subscriptions)

## Run locally

```bash
cd /home/praveen/apexneural/razorpay/razorpay_fastapi

# (recommended) use your existing venv
source /home/praveen/apexneural/razorpay/venv/bin/activate

pip install -r requirements.txt

# copy env and fill values
cp .env.example .env

uvicorn main:app --host 0.0.0.0 --port 8000
```

API docs:
- Swagger UI: `http://localhost:8000/docs`

## Environment variables

Required in `.env`:
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET` (required to accept webhooks)
- `DATABASE_URL` (Postgres async URL, e.g. `postgresql+asyncpg://postgres:postgres@localhost:5432/razorpay_db`)

## Health

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
curl -s http://localhost:8000/health/db | python3 -m json.tool
```

## Orders (amount in paise)

### Create order (send rupees, server stores/creates in paise)

```bash
curl -X POST "http://localhost:8000/api/v1/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 100.0,
    "currency": "INR",
    "receipt": "receipt_001",
    "notes": { "purpose": "demo" }
  }' | python3 -m json.tool
```

### List orders (from DB)

```bash
curl -s "http://localhost:8000/api/v1/orders" | python3 -m json.tool
```

### Get order (from Razorpay)

```bash
curl -s "http://localhost:8000/api/v1/orders/{order_id}" | python3 -m json.tool
```

### Get order (from DB)

```bash
curl -s "http://localhost:8000/api/v1/orders/{order_id}/db" | python3 -m json.tool
```

## Payments

> Note: creating an **order** does not create a **payment**. A payment exists only after a user completes checkout.

### Verify payment signature (auto-captures if authorized)

Frontend Razorpay Checkout returns:
- `razorpay_order_id`
- `razorpay_payment_id`
- `razorpay_signature`

```bash
curl -X POST "http://localhost:8000/api/v1/payments/verify" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "order_xxx",
    "payment_id": "pay_xxx",
    "signature": "sig_xxx"
  }' | python3 -m json.tool
```

### Capture payment (manual; usually not needed if you verify)

```bash
curl -X POST "http://localhost:8000/api/v1/payments/capture" \
  -H "Content-Type: application/json" \
  -d '{
    "payment_id": "pay_xxx",
    "amount": 100.0
  }' | python3 -m json.tool
```

### List payments (from DB)

```bash
curl -s "http://localhost:8000/api/v1/payments" | python3 -m json.tool
```

### Get payment (from Razorpay)

```bash
curl -s "http://localhost:8000/api/v1/payments/{payment_id}" | python3 -m json.tool
```

### Get payment (from DB)

```bash
curl -s "http://localhost:8000/api/v1/payments/{payment_id}/db" | python3 -m json.tool
```

## Webhooks

Endpoint:
- `POST /api/v1/webhooks/razorpay`

Razorpay will send `X-Razorpay-Signature` header. You must set `RAZORPAY_WEBHOOK_SECRET`.

Example (will fail unless signature is valid):

```bash
curl -X POST "http://localhost:8000/api/v1/webhooks/razorpay" \
  -H "Content-Type: application/json" \
  -H "X-Razorpay-Signature: <signature>" \
  -d '{
    "entity": "event",
    "event": "payment.captured",
    "payload": {},
    "created_at": 1234567890
  }' | python3 -m json.tool
```

## Subscriptions

### Create plan

```bash
curl -X POST "http://localhost:8000/api/v1/subscriptions/plans" \
  -H "Content-Type: application/json" \
  -d '{
    "period": "monthly",
    "interval": 1,
    "item": {
      "name": "Basic Monthly",
      "amount": 50.0,
      "currency": "INR",
      "description": "Monthly subscription"
    },
    "notes": { "tier": "basic" }
  }' | python3 -m json.tool
```

### List plans

```bash
curl -s "http://localhost:8000/api/v1/subscriptions/plans?count=10&skip=0" | python3 -m json.tool
```

### Get plan

```bash
curl -s "http://localhost:8000/api/v1/subscriptions/plans/{plan_id}" | python3 -m json.tool
```

### Create subscription

```bash
curl -X POST "http://localhost:8000/api/v1/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "plan_xxx",
    "customer_notify": 1,
    "quantity": 1,
    "total_count": 12,
    "notes": { "purpose": "demo" }
  }' | python3 -m json.tool
```

### List subscriptions (from Razorpay)

```bash
curl -s "http://localhost:8000/api/v1/subscriptions?count=10&skip=0" | python3 -m json.tool
```

### List subscriptions (from DB)

```bash
curl -s "http://localhost:8000/api/v1/subscriptions/db/list?skip=0&limit=100" | python3 -m json.tool
```

### Get subscription

```bash
curl -s "http://localhost:8000/api/v1/subscriptions/{subscription_id}" | python3 -m json.tool
```

### Pause / Resume / Cancel

```bash
# pause
curl -X POST "http://localhost:8000/api/v1/subscriptions/{subscription_id}/pause" \
  -H "Content-Type: application/json" \
  -d '{"pause_at":"immediate"}' | python3 -m json.tool

# resume
curl -X POST "http://localhost:8000/api/v1/subscriptions/{subscription_id}/resume" \
  -H "Content-Type: application/json" \
  -d '{"resume_at":"immediate"}' | python3 -m json.tool

# cancel
curl -X POST "http://localhost:8000/api/v1/subscriptions/{subscription_id}/cancel" \
  -H "Content-Type: application/json" \
  -d '{"cancel_at_cycle_end":false}' | python3 -m json.tool
```

### Invoices

```bash
curl -s "http://localhost:8000/api/v1/subscriptions/{subscription_id}/invoices" | python3 -m json.tool
curl -s "http://localhost:8000/api/v1/subscriptions/invoices/{invoice_id}" | python3 -m json.tool
```

## Simple HTML frontends (optional)

- `subscription_frontend.html` (plans/subscriptions/invoices)
- `complete_payment.html` (order + checkout + verify)
- `test_payment_capture.html`, `test_50_rupees.html`

Serve them:

```bash
cd /home/praveen/apexneural/razorpay/razorpay_fastapi
python3 -m http.server 8080
```

Open:
- `http://localhost:8080/subscription_frontend.html`
- `http://localhost:8080/complete_payment.html`

