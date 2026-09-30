# Load test — 100k tickets, API_WORKERS=2, production compose on Docker Desktop

Local, single machine (Intel64 Family 6 Model 186 Stepping 3, GenuineIntel; Docker VM 12 CPUs, 7.6 GiB), production compose stack behind Caddy, load generator on the same machine. SYNTHETIC load-test organization with 100000 tickets. Steady state 120 s per step after ramp-up. git `80f1e0d4a1`. SLO: p95 < 500 ms per endpoint group, < 1% errors.

| Users | Requests/s | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Within SLO | Slowest group (p95) |
|---|---|---|---|---|---|---|---|
| 50 | 14.9 | 59 | 120 | 380 | 7.02% | no | GET /analytics/overview (600 ms) |
| 100 | 28.9 | 59 | 140 | 380 | 8.88% | no | GET /analytics/overview (460 ms) |
| 250 | 70.7 | 90 | 360 | 670 | 9.44% | no | GET /analytics/overview (1000 ms) |
| 500 | 56.5 | 6 | 60000 | 66000 | 95.74% | no | GET /analytics/overview (60000 ms) |

## Endpoint groups at 500 users

| Endpoint | Requests | Req/s | p50 | p95 | p99 | Failures |
|---|---|---|---|---|---|---|
| GET /analytics/overview | 216 | 1.9 | 7 | 60000 | 66000 | 197 |
| GET /tickets (SLA at risk) | 142 | 1.2 | 6 | 60000 | 67000 | 129 |
| GET /tickets (queue) | 618 | 5.3 | 6 | 60000 | 66000 | 581 |
| GET /tickets (requester) | 1480 | 12.7 | 9 | 60000 | 67000 | 1369 |
| GET /tickets/{id} | 714 | 6.1 | 6 | 60000 | 60000 | 701 |
| POST /tickets | 276 | 2.4 | 13 | 60000 | 67000 | 276 |
| GET /tickets (my work) | 603 | 5.2 | 6 | 59000 | 66000 | 565 |
| GET /tickets?q= (search) | 188 | 1.6 | 6 | 41000 | 60000 | 175 |
| GET /kb/search | 604 | 5.2 | 9 | 8200 | 13000 | 604 |
| POST /tickets/{id}/comments | 119 | 1.0 | 5 | 2100 | 60000 | 114 |
| GET /analytics/ai-performance | 59 | 0.5 | 6 | 79 | 60000 | 58 |
| GET /tickets/{id}/comments | 718 | 6.2 | 5 | 74 | 1100 | 703 |
| GET /tickets/{id}/history | 415 | 3.6 | 5 | 16 | 900 | 407 |
| GET /tickets/{id}/ai | 416 | 3.6 | 5 | 14 | 2000 | 409 |

Container CPU / memory half-way through the last step: nexadesk-load-caddy-1 4.55% 89.68MiB / 7.603GiB; nexadesk-load-worker-1 0.07% 230.4MiB / 7.603GiB; nexadesk-load-backend-1 2.52% 289.9MiB / 7.603GiB; nexadesk-load-grafana-1 16.51% 138.3MiB / 7.603GiB; nexadesk-load-prometheus-1 0.00% 34.83MiB / 7.603GiB; nexadesk-load-redis-1 1.05% 6.434MiB / 7.603GiB; nexadesk-load-postgres-1 12.46% 320.3MiB / 7.603GiB; nexadesk-load-web-1 0.00% 9.816MiB / 7.603GiB; procurax-postgres 0.01% 54.75MiB / 7.603GiB; nexadesk-pg-test 0.00% 159.7MiB / 7.603GiB.
