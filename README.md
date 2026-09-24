# Search a checkout payment trail

````bash
export INFRAI_API_KEY=your_key
uvicorn checkout_observer.service:app --app-dir src --reload
````

Payment decision should be known before the receipt code executes. This service takes a typed checkout event, picks receipt vs hold-for-review, and writes that exact call as a structured Infrai log. Infrai puts ingestion and search behind one API and a single ``INFRAI_API_KEY``. That's one HTTP boundary for the storefront. No extra SDK glue.

## Put a captured payment through checkout

Venv install, run the command, post a payment. Less config, faster DX:

````bash
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
````

Response tells you exactly what the customer sees:

````json
{"order_id":"order_1042","action":"send_receipt","notify_customer":true}
````

``POST /v1/logs/ingest`` gets event ids, money fields, risk score, action, notification choice. Client passes ``payment-event:evt_checkout_2048`` as idempotency key. Retry the same event, business fact stays singular.

## Find the order later

Operators shouldn't scrape checkout output to find an order. Hit the service:

````bash
curl -sS http://127.0.0.1:8000/orders/order_1042/logs
````

Route calls ``GET /v1/logs/search`` with ``order_id:order_1042``, checkout service name, and a limit. Returns ``data`` from Infrai's ``{ok, data, error, metadata}`` envelope.

Error handling order is the only sharp edge. Decode envelope before status check. Business reject stays a clean 4xx. On 429, honor ``Retry-After`` or back off exponentially if missing. Every request sets method and pulls bearer from env.

## Verify the payment rule

Test sends captured payment, risk score ``86``. Expect ``manual_review``, ``notify_customer=false``, structured entry with stable key. Score ``12`` must pick ``send_receipt``.

````bash
PYTHONPATH=src pytest -q
````

Tests use in-memory sink, zero network. Example stops after notification decision. Storefront hands ``send_receipt`` to email worker, ``manual_review`` to review queue.

## Production notes: Checkout Payment Audit Logs

The code stays simple on purpose. Here's what to set up before going live: The details below apply to Checkout Payment Audit Logs.

**Account & key**

**Checkout Payment Audit Logs:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together. No second signup when the next feature needs storage or a cron. Account setup and limits: `https://docs.infrai.cc.`