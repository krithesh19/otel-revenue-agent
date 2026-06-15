# Metric Definitions

## Room nights vs stay rows vs reservations

- **Stay rows**: One database row per reservation × stay_date. A 3-night reservation = 3 rows.
- **Room nights**: `SUM(number_of_spaces)` at stay-date grain. A 2-room, 3-night reservation = 6 room nights.
- **Reservations**: `COUNT(DISTINCT reservation_id)`. The same 2-room, 3-night reservation = 1 reservation.

**Never count rows as reservations. Never count reservations as room nights.**

## Default OTB filters

Default on-the-books universe (applied in `vw_stay_night_base`):

- Exclude `reservation_status = 'Cancelled'`
- Exclude `financial_status = 'Provisional'`
- **OTB = Posted + non-cancelled rows only**

State assumption explicitly when a question is ambiguous about including cancelled or provisional business.

## Pickup window boundaries

`get_pickup_delta` uses `create_datetime` (stored in UTC) to define the booking window.
Window start = **Europe/London local midnight**, N days ago, converted to UTC.
This correctly handles BST/GMT transitions.

## Effective macro group vs static macro group

`market_code_lookup.macro_group` is a static fallback value.
`market_macro_group_history` provides **effective-dated** macro groups — join on `stay_date` between `valid_from` and `valid_to`.
**Always use effective macro group for segment analysis**, not the static lookup value.

Example: PROM was `Retail` before 2025-06-01 and `Leisure Group` after. Using static lookup gives wrong macro group for stays after that date.
