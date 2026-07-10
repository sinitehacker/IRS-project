# Design

The service uses a small hexagonal-style split: HTTP routing validates/translates requests while the pure `calculate` function owns pricing rules. Promotions are data records, so their values, priorities, store scope, activation windows, and caps can be changed through the API without deploys.

The in-memory store makes the service reviewable with zero setup. A production adapter would replace `PROMOTIONS`, `TIERS`, and `AUDIT` with transactional persistence, retaining the same calculation contract. Optimistic versions are already included on promotions for that migration.
