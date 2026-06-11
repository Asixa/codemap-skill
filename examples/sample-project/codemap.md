<!--
  This file:        .codemap/codemap.md   (written report)
  Interactive map:  .codemap/codemap.html
-->

# Acme Storefront — Functional Module Quality Audit

> **Interactive view:** [`.codemap/codemap.html`](codemap.html) — per-module scores, findings, LoC, and the dependency graph. This file is the written report.

**Generated:** 2026-01-01 · **Modules:** 49 · **Size:** ≈ 28,600 LoC · 214 files (sample)

## Health by layer

| Layer | Modules | Avg score |
|---|--:|--:|
| Frontend · Shell & Routing | 3 | 87 |
| Frontend · Pages | 7 | 73 |
| Frontend · State Stores | 6 | 79 |
| Frontend · Transport | 5 | 80 |
| Backend · API Routes | 6 | 77 |
| Backend · Services | 8 | 73 |
| Backend · Domain Core | 5 | 89 |
| Backend · Persistence | 3 | 82 |
| Backend · Workers & Jobs | 3 | 77 |
| Integrations | 3 | 74 |

## Per-module lines of code & score

_LoC is the representative file/folder per module; folder-level modules overlap and are not additive._

### Frontend · Shell & Routing

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| App Shell | 420 | 84 B | — |
| Navigation | 240 | 88 B | — |
| Router | 180 | 90 A | — |

### Frontend · Pages

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| Admin | 2,100 | 66 C | bloat, any-escape |
| Checkout | 1,860 | 58 D | god-component, dual-format, fallback |
| Cart | 1,420 | 70 C | god-component |
| Product | 1,240 | 72 C | bloat |
| Catalog | 980 | 78 B | — |
| Account | 760 | 82 B | — |
| Search | 540 | 84 B | — |

### Frontend · State Stores

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| checkoutStore | 480 | 62 C | dual-format, legacy |
| catalogStore | 410 | 86 B | — |
| cartStore | 360 | 74 C | duplication |
| authStore | 290 | 80 B | — |
| searchStore | 220 | 82 B | — |
| uiStore | 150 | 88 B | — |

### Frontend · Transport

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| apiClient | 690 | 68 C | glue, bloat |
| wsClient | 230 | 84 B | — |
| adminClient | 180 | 80 B | — |
| paymentsClient | 140 | 86 B | — |
| pricingClient | 110 | 84 B | — |

### Backend · API Routes

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| orders routes | 610 | 74 C | dual-format |
| API Gateway | 540 | 88 B | — |
| payments routes | 480 | 55 D | stub, fallback |
| auth routes | 420 | 78 B | silent-except |
| products routes | 360 | 84 B | — |
| search routes | 240 | 82 B | — |

### Backend · Services

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| OrderService | 1,480 | 64 C | duplication, bloat |
| PricingEngine | 880 | 70 C | over-fit |
| InventoryService | 540 | 78 B | — |
| AuthService | 520 | 80 B | — |
| SearchService | 470 | 76 B | fallback |
| CatalogService | 430 | 86 B | — |
| NotificationService | 300 | 84 B | — |
| PaymentService | 260 | 48 D | stub, fake-output |

### Backend · Domain Core

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| Order | 380 | 88 B | — |
| Product | 260 | 90 A | — |
| User | 210 | 88 B | — |
| Money | 120 | 92 A | — |
| TokenUtil | 90 | 86 B | — |

### Backend · Persistence

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| Repository | 640 | 72 C | duplication |
| Migrations | 220 | 85 B | — |
| DB Pool | 180 | 90 A | — |

### Backend · Workers & Jobs

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| WebhookDispatcher | 340 | 68 C | silent-except, legacy |
| EmailWorker | 260 | 80 B | — |
| Templates | 150 | 84 B | — |

### Integrations

| Module | LoC | Score | Tags |
|---|--:|:--|:--|
| Stripe Gateway | 280 | 78 B | — |
| Shipping Provider | 230 | 74 C | glue |
| Analytics | 190 | 70 C | silent-except |

## Worst offenders

- **PaymentService (48/D)** — services/payment.py:31: charge()/refund() return a canned `{status:'succeeded'}` — sandbox stub, no real gateway call.
- **payments routes (55/D)** — api/payments.py:44: webhook handler always returns 200 without verifying the signature (stub).
- **Checkout (58/D)** — src/pages/Checkout.tsx: 1860-line god-component mixing the address/shipping/payment steps, validation and direct API calls.
- **checkoutStore (62/C)** — src/stores/checkout.ts:40: reads both snake_case and camelCase address fields (dual-format).
- **OrderService (64/C)** — services/order.py: 1480-line service; the order state machine is duplicated between place() and fulfill().
- **Admin (66/C)** — src/pages/Admin.tsx: 2100-line page: reports, tables and editors all in one file.
- **apiClient (68/C)** — src/transport/apiClient.ts: ~50 one-line get/post wrappers that only forward args (glue) — generate or collapse to a typed client.
- **WebhookDispatcher (68/C)** — workers/webhooks.py:55: `except: pass` swallows delivery errors — failed webhooks vanish.
- **Cart (70/C)**
- **PricingEngine (70/C)** — services/pricing.py:120: discount rules hardcoded to the current promo set (over-fit).

## All findings

### HIGH (4)

- **Checkout** · `src/pages/Checkout.tsx` — 1860-line god-component mixing the address/shipping/payment steps, validation and direct API calls.
- **payments routes** · `api/payments.py:44` — webhook handler always returns 200 without verifying the signature (stub).
- **OrderService** · `services/order.py` — 1480-line service; the order state machine is duplicated between place() and fulfill().
- **PaymentService** · `services/payment.py:31` — charge()/refund() return a canned `{status:'succeeded'}` — sandbox stub, no real gateway call.

### MED (13)

- **Product** · `src/pages/Product.tsx` — 1240-line component: gallery, variant picker and reviews in one file.
- **Checkout** · `src/pages/Checkout.tsx:412` — reads both `postal_code` and `postalCode` from the address form (dual-format).
- **Admin** · `src/pages/Admin.tsx` — 2100-line page: reports, tables and editors all in one file.
- **cartStore** · `src/stores/cart.ts:90` — cart totals re-implemented here and in PricingEngine (duplication).
- **checkoutStore** · `src/stores/checkout.ts:40` — reads both snake_case and camelCase address fields (dual-format).
- **apiClient** · `src/transport/apiClient.ts` — ~50 one-line get/post wrappers that only forward args (glue) — generate or collapse to a typed client.
- **orders routes** · `api/orders.py:88` — accepts both the legacy and v2 cart payload shapes (dual-format).
- **payments routes** · `api/payments.py:70` — falls back to marking the order paid when the provider call times out.
- **OrderService** · `services/order.py:620` — inventory reservation logic copy-pasted from InventoryService.
- **PricingEngine** · `services/pricing.py:120` — discount rules hardcoded to the current promo set (over-fit).
- **PaymentService** · `services/payment.py:88` — 'TODO: wire the real provider before launch.'
- **Repository** · `data/repo.py` — per-entity CRUD copy-pasted across 9 repositories — extract a base.
- **WebhookDispatcher** · `workers/webhooks.py:55` — `except: pass` swallows delivery errors — failed webhooks vanish.

### LOW (9)

- **Checkout** · `src/pages/Checkout.tsx:980` — silent catch around the shipping-rate fetch falls back to a flat rate.
- **Admin** · `src/pages/Admin.tsx:300` — several `as any` casts around the chart library.
- **checkoutStore** · `src/stores/checkout.ts:8` — legacy single-step draft kept for old links.
- **apiClient** · `src/transport/apiClient.ts:1` — one 690-line file mixing transport with the whole endpoint surface.
- **auth routes** · `api/auth.py:140` — broad except around the OAuth token exchange logs but swallows the cause.
- **SearchService** · `services/search.py:80` — documented fallback to SQL LIKE when Elasticsearch is unreachable.
- **WebhookDispatcher** · `workers/webhooks.py:12` — legacy v1 payload path kept alongside v2.
- **Shipping Provider** · `integrations/shipping.py` — adapter forwards every field unchanged (glue).
- **Analytics** · `integrations/analytics.py:22` — fire-and-forget send swallows failures silently.

## Cross-cutting themes

- **Payments is the weakest area.** PaymentService and the payments routes are still sandbox stubs (fake-output / stub) — real provider integration is unfinished, yet it is already wired into checkout.
- **Checkout and Order carry the most debt.** checkout_page, cartStore and OrderService are god-components with duplicated state-machine logic; the multi-step checkout mixes UI, validation and API calls in one file.
- **Dual-format is creeping in at the order boundary.** orders routes, checkoutStore and the checkout page accept both legacy and v2 payload shapes — normalize once at the transport layer instead.
- **apiClient is mostly glue.** ~50 near-identical endpoint wrappers add no value; generate them or collapse to a single typed client.

