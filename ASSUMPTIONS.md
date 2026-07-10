# Assumptions

- Money is represented as decimal-like JSON numbers and rounded to two places at response boundaries.
- Promotions stack in ascending `priority` after the customer-tier slab discount.
- The in-memory repository is intentionally ephemeral and seeded through the promotion API.
- Time windows are inclusive and use `HH:MM` local store time supplied in request context.
