# Load test — after P11: dashboard cache + trigram search + model warm-up (100k tickets, API_WORKERS=2)

Local, single machine (Intel64 Family 6 Model 186 Stepping 3, GenuineIntel; Docker VM 12 CPUs, 7.6 GiB), production compose stack behind Caddy, load generator on the same machine. SYNTHETIC load-test organization with 100000 tickets. Steady state 120 s per step after ramp-up. git `80f1e0d4a1`. SLO: p95 < 500 ms per endpoint group, < 1% errors.

| Users | Requests/s | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Within SLO | Slowest group (p95) |
|---|---|---|---|---|---|---|---|
| 50 | 14.5 | 54 | 130 | 220 | 0.28% | no | GET /analytics/overview (520 ms) |
| 100 | 24.0 | 160 | 3300 | 7900 | 3.10% | no | GET /tickets (queue) (6100 ms) |
| 250 | 24.7 | 130 | 40000 | 60000 | 13.50% | no | GET /analytics/ai-performance (60000 ms) |
| 500 | 44.1 | 6 | 60000 | 71000 | 96.90% | no | GET /analytics/ai-performance (70000 ms) |

## Endpoint groups at 500 users

| Endpoint | Requests | Req/s | p50 | p95 | p99 | Failures |
|---|---|---|---|---|---|---|
| GET /analytics/ai-performance | 59 | 0.5 | 6 | 70000 | 71000 | 57 |
| GET /kb/search | 550 | 4.3 | 6 | 67000 | 73000 | 533 |
| GET /tickets (SLA at risk) | 147 | 1.1 | 7 | 67000 | 72000 | 138 |
| POST /tickets | 297 | 2.3 | 6 | 66000 | 72000 | 296 |
| GET /analytics/overview | 192 | 1.5 | 6 | 65000 | 71000 | 185 |
| GET /tickets (requester) | 1416 | 11.1 | 6 | 61000 | 71000 | 1356 |
| GET /tickets (my work) | 561 | 4.4 | 6 | 60000 | 72000 | 534 |
| GET /tickets (queue) | 561 | 4.4 | 6 | 60000 | 72000 | 543 |
| GET /tickets?q= (search) | 191 | 1.5 | 6 | 60000 | 70000 | 181 |
| POST /tickets/{id}/comments | 77 | 0.6 | 6 | 60000 | 60000 | 76 |
| GET /tickets/{id} | 519 | 4.1 | 5 | 58000 | 60000 | 511 |
| POST /tickets (429 per-IP limit, expected) | 8 | 0.1 | 13000 | 14000 | 14000 | 0 |
| GET /tickets/{id}/comments | 518 | 4.0 | 5 | 58 | 130 | 515 |
| GET /tickets/{id}/ai | 272 | 2.1 | 4 | 17 | 26 | 270 |
| GET /tickets/{id}/history | 272 | 2.1 | 5 | 15 | 110 | 270 |

Container CPU / memory half-way through the last step: nexadesk-load-worker-1 0.43% 234MiB / 7.603GiB; nexadesk-load-backend-1 0.85% 601.5MiB / 7.603GiB; nexadesk-load-caddy-1 2.01% 84.29MiB / 7.603GiB; nexadesk-load-grafana-1 1.22% 135.5MiB / 7.603GiB; nexadesk-load-prometheus-1 0.00% 35.14MiB / 7.603GiB; nexadesk-load-redis-1 0.73% 6.531MiB / 7.603GiB; nexadesk-load-postgres-1 0.48% 372.4MiB / 7.603GiB; nexadesk-load-web-1 0.00% 9.805MiB / 7.603GiB; procurax-postgres 0.01% 54.75MiB / 7.603GiB; nexadesk-pg-test 0.00% 159.7MiB / 7.603GiB.
