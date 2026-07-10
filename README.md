# ShopperStop Promotional Pricing Engine

A zero-dependency REST service for configurable retail pricing. It calculates progressive customer-tier discounts and stacks data-driven promotions with an auditable management API.

## Run

Requires Python 3.9+.

```bash
python app.py
```

Or run with Docker: `docker build -t shoppers-stop . && docker run -p 8000:8000 shoppers-stop`.

## Verify

```bash
python -m unittest -v
curl http://localhost:8000/health
```

## Main API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/bills/calculate` | Calculate a bill and return attribution per discount |
| `POST, GET /api/v1/promotions` | Create/list data-driven promotions |
| `GET, PUT, DELETE /api/v1/promotions/{id}` | Read, update, soft-delete a promotion |
| `POST /api/v1/promotions/{id}/activate` | Enable a promotion |
| `POST /api/v1/promotions/{id}/deactivate` | Disable a promotion |
| `POST /api/v1/promotions/simulate` | Preview an unsaved promotion against a bill |
| `GET, POST /api/v1/customer-tiers` | Manage progressive discount tiers |
| `GET /openapi.json` | Lightweight OpenAPI 3 contract |

### Calculate a bill

```bash
curl -X POST http://localhost:8000/api/v1/bills/calculate \
  -H 'Content-Type: application/json' \
  -d '{"customer":{"tier":"premium"},"items":[{"name":"TV","category":"Electronics","quantity":1,"unitPrice":15000}]}'
```

The response for this request has a `finalTotal` of `12000`, with the progressive slab breakdown included in `appliedDiscounts`.

### Create and enable a promotion

```bash
curl -X POST http://localhost:8000/api/v1/promotions -H 'Content-Type: application/json' \
  -d '{"name":"Weekend coupon","type":"PERCENTAGE","value":10,"priority":10,"maxDiscount":1000}'
curl -X POST http://localhost:8000/api/v1/promotions/<id>/activate
```

Supported promotion types: `FLAT`, `PERCENTAGE`, `CATEGORY`, `BUY_X_GET_Y`, and `TIME`. A promotion can also set `minimumOrder`, `category`, `timeWindow`, `storeIds`, `maxDiscount`, and `priority`.

## Configuration and design

Customer slabs and promotions are API-managed JSON configuration. See [DESIGN.md](DESIGN.md), [ASSUMPTIONS.md](ASSUMPTIONS.md), and [TESTING.md](TESTING.md) for architecture, operational assumptions, and test details.
