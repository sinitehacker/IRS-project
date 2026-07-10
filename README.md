#  ShopperStop Promotional Pricing Engine

A configuration-driven retail pricing engine developed as part of the **IRS Backend Engineering Assignment**.

The project provides a REST API for calculating customer bills using progressive slab-based discounts and configurable promotions. It also includes a lightweight web interface for testing pricing scenarios, interactive API documentation (Swagger), and a health monitoring endpoint.

The system is designed to be extensible, allowing new promotion types and pricing rules to be managed without changing application code.

---

#  Features

## Billing Engine

- Progressive slab-based customer discounts
- Regular and Premium customer tiers
- Multiple cart items
- Detailed discount attribution
- Savings summary
- Indian currency formatting

## Promotion Engine

- Create, update, view and soft-delete promotions
- Activate and deactivate promotions
- Promotion simulation before activation
- Configurable priorities
- Data-driven promotion rules
- Promotion stacking support

Supported promotion types:

- Slab Based
- Flat Discount
- Percentage Discount
- Category Discount
- Buy-X-Get-Y
- Time-Based Promotions

---

#  Web Interface

The project includes a simple frontend for testing pricing scenarios without manually sending API requests.

### Available Pages

| Service | URL |
|----------|-----|
| Calculator UI | http://localhost:8000 |
| Interactive Swagger UI | http://localhost:8000/docs |
| OpenAPI JSON | http://localhost:8000/openapi.json |
| Health Check | http://localhost:8000/health |

The Calculator UI provides:

- Customer Tier selection
- Store ID
- Coupon Code
- Timestamp
- Preview Mode
- JSON Cart Editor
- Bill Summary
- Applied Discounts
- Active Promotions
- Raw API Response Viewer

---

#  Architecture

```
                 Frontend (HTML/CSS/JavaScript)
                             │
                             ▼
                    FastAPI REST Endpoints
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
 Bill Service        Promotion Service     Discount Engine
                             │
                             ▼
                 In-Memory Configuration Store
```

The application follows a layered architecture to keep business logic separate from API and presentation layers.

---

#  Discount Logic

## Regular Customers

| Purchase Amount | Discount |
|-----------------|----------|
| ₹0 – ₹5,000 | 0% |
| ₹5,001 – ₹10,000 | 10% |
| Above ₹10,000 | 20% |

---

## Premium Customers

| Purchase Amount | Discount |
|-----------------|----------|
| ₹0 – ₹5,000 | 10% |
| ₹5,001 – ₹10,000 | 20% |
| Above ₹10,000 | 30% |

Discounts are applied progressively across slabs rather than using a flat percentage.

Example:

Purchase Amount = ₹15,000 (Premium)

- First ₹5,000 → 10%
- Next ₹5,000 → 20%
- Remaining ₹5,000 → 30%

Total Discount = ₹3,000

Final Total = ₹12,000

---

#  Running the Project

## Requirements

- Python 3.9+
- pip

## Run Locally

```bash
python app.py
```

The application will start on:

```
http://localhost:8000
```

---

## Docker

```bash
docker build -t shoppers-stop .
docker run -p 8000:8000 shoppers-stop
```

---

#  Running Tests

```bash
python -m unittest -v
```

Health Check

```bash
curl http://localhost:8000/health
```

---

# REST API

## Bill APIs

| Method | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/v1/bills/calculate` | Calculate customer bill |

---

## Promotion APIs

| Method | Endpoint |
|---------|----------|
| POST | `/api/v1/promotions` |
| GET | `/api/v1/promotions` |
| GET | `/api/v1/promotions/{id}` |
| PUT | `/api/v1/promotions/{id}` |
| DELETE | `/api/v1/promotions/{id}` |
| POST | `/api/v1/promotions/{id}/activate` |
| POST | `/api/v1/promotions/{id}/deactivate` |
| POST | `/api/v1/promotions/simulate` |

---

## Customer Tier APIs

| Method | Endpoint |
|---------|----------|
| GET | `/api/v1/customer-tiers` |
| POST | `/api/v1/customer-tiers` |

---

# Sample Bill Calculation

```bash
curl -X POST http://localhost:8000/api/v1/bills/calculate \
-H "Content-Type: application/json" \
-d '{
  "customer": {
    "tier":"premium"
  },
  "items":[
    {
      "name":"TV",
      "category":"Electronics",
      "quantity":1,
      "unitPrice":15000
    }
  ]
}'
```

Response

- Final Total: ₹12,000
- Progressive slab breakdown
- Discount attribution
- Savings percentage

---

#  Promotion Example

Create a Promotion

```bash
curl -X POST http://localhost:8000/api/v1/promotions \
-H "Content-Type: application/json" \
-d '{
  "name":"Weekend Coupon",
  "type":"PERCENTAGE",
  "value":10,
  "priority":10,
  "maxDiscount":1000
}'
```

Activate Promotion

```bash
curl -X POST http://localhost:8000/api/v1/promotions/{id}/activate
```

---

#  Configuration

Business rules are completely configuration-driven.

Administrators can configure:

- Customer discount slabs
- Promotion priorities
- Stacking rules
- Category mappings
- Time windows
- Store-specific promotions
- Maximum discount limits

No code changes are required to modify pricing rules.

---

# Project Structure

```
app.py
controllers/
services/
models/
config/
templates/
static/
tests/
```

---

# Tech Stack

- Python 3
- FastAPI
- HTML
- CSS
- JavaScript
- OpenAPI / Swagger
- Uvicorn
- unittest

---

#  Documentation

Additional documentation included in this repository:

- DESIGN.md
- TESTING.md
- ASSUMPTIONS.md
- SUBMISSION.md

---

#Output 
<img width="1132" height="610" alt="image" src="https://github.com/user-attachments/assets/65cf2600-a2f1-41fe-8fb8-2b05f5710a05" />
<img width="1132" height="610" alt="image" src="https://github.com/user-attachments/assets/ff2031c7-0a7a-418f-97c8-a8652545c49b" />
<img width="1132" height="610" alt="image" src="https://github.com/user-attachments/assets/13875a5f-7080-4c9f-86cb-3dbe1c6ff2cb" />


---

