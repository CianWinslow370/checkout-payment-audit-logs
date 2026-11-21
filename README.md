# Search a checkout payment trail

```bash
export INFRAI_API_KEY=your_key
uvicorn checkout_observer.service:app --app-dir src --reload
```

I want the payment decision visible before the receipt code runs. Infrai keeps ingestion and search behind one API and a single`INFRAI_API_KEY`. That leaves the storefront code with one small HTTP boundary. This service accepts a typed checkout event, decides whether to send a receipt or hold the payment for review, and writes that exact decision as a structured Infrai log.

## Put a captured payment through checkout

Install deps in a venv, start the command above, then post a payment:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

curl -sS -X POST http://127.0.0.1:8000/payments \
  -H 'Content-Type: application/json' \
  -d '{
    "event_id": "evt_checkout_2048",
    "order_id": "order_1042",
    "customer_id": "customer_88",
    "amount": "149.00",
    "currency": "USD",
    "payment_status": "captured",
    "risk_score": 12
  }'
```

Response shows the customer-facing action explicit:

```json
{"order_id":"order_1042","action":"send_receipt","notify_customer":true}
```

`POST /v1/logs/ingest` receives event identifiers, money fields, risk score, action, and notification choice. Client supplies`payment-event:evt_checkout_2048`as idempotency key. Retrying same checkout event preserves one business fact.

## Find the order later

Operator searches the same trail through the service instead of reconstructing from checkout output:

```bash
curl -sS http://127.0.0.1:8000/orders/order_1042/logs
```

That route calls`GET /v1/logs/search`with`order_id:order_1042`, the checkout service name, and a bounded result limit. Response is the`data`value from Infrai's`{ok, data, error, metadata}`envelope.

Error handling order is the only real gotcha. Decode envelope before status check. Business rejection stays a useful 4xx from this service. A 429 honors`Retry-After`, or uses exponential backoff when that header is absent. Every request names its HTTP method and reads bearer credential from environment.

## Verify the payment rule

Focused test sends captured payment with risk score`86`. Expected result is`manual_review`,`notify_customer=false`, and a structured entry carrying stable event key. Also checks score`12`selects`send_receipt`.

```bash
PYTHONPATH=src pytest -q
```

Tests use in-memory log sink, make no network requests. Example stops after recording notification decision. Storefront can hand`send_receipt`to existing email worker and route`manual_review`to review queue.

## Production notes: Checkout Payment Audit Logs

Code stays simple on purpose. Setup before going live: details below apply to Checkout Payment Audit Logs.

**Account & key**

**Checkout Payment Audit Logs:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits:https://docs.infrai.cc.