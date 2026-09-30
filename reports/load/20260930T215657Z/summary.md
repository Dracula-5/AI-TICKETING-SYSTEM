# Load test — fixes + backpressure: API_WORKERS=2, --limit-concurrency 30 (100k tickets)

Local, single machine (Intel64 Family 6 Model 186 Stepping 3, GenuineIntel; Docker VM 12 CPUs, 7.6 GiB), production compose stack behind Caddy, load generator on the same machine. SYNTHETIC load-test organization with 100000 tickets. Steady state 120 s per step after ramp-up. git `80f1e0d4a1`. SLO: p95 < 500 ms per endpoint group, < 1% errors.

| Users | Requests/s | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Within SLO | Slowest group (p95) |
|---|---|---|---|---|---|---|---|
| 250 | 68.5 | 150 | 540 | 1000 | 1.21% | no | POST /tickets (1300 ms) |
| 500 | 132.3 | 71 | 820 | 1200 | 66.89% | no | POST /tickets (1300 ms) |

## Endpoint groups at 500 users

| Endpoint | Requests | Req/s | p50 | p95 | p99 | Failures |
|---|---|---|---|---|---|---|
| POST /tickets | 452 | 3.7 | 9 | 1300 | 1700 | 400 |
| GET /kb/search | 863 | 7.1 | 7 | 1100 | 1500 | 764 |
| GET /analytics/ai-performance | 123 | 1.0 | 99 | 1000 | 1300 | 78 |
| POST /tickets/{id}/comments | 270 | 2.2 | 84 | 1000 | 1300 | 173 |
| POST /tickets (429 per-IP limit, expected) | 135 | 1.1 | 550 | 920 | 2200 | 0 |
| GET /analytics/overview | 407 | 3.3 | 78 | 900 | 1500 | 271 |
| GET /kb/search (429 per-IP limit, expected) | 270 | 2.2 | 490 | 850 | 2300 | 0 |
| GET /tickets?q= (search) | 346 | 2.8 | 89 | 850 | 1100 | 217 |
| GET /tickets (SLA at risk) | 264 | 2.2 | 97 | 840 | 1600 | 168 |
| GET /tickets (requester) | 2963 | 24.3 | 83 | 840 | 1300 | 1956 |
| GET /tickets (my work) | 1038 | 8.5 | 95 | 820 | 1100 | 654 |
| GET /tickets (queue) | 1073 | 8.8 | 78 | 800 | 1100 | 705 |
| GET /tickets/{id}/comments | 2704 | 22.2 | 57 | 770 | 1000 | 1862 |
| GET /tickets/{id} | 2698 | 22.1 | 75 | 760 | 1100 | 1808 |
| GET /tickets/{id}/ai | 1272 | 10.4 | 39 | 730 | 980 | 880 |
| GET /tickets/{id}/history | 1271 | 10.4 | 49 | 720 | 1000 | 866 |

Container CPU / memory half-way through the last step: nexadesk-load-worker-1 298.22% 239.9MiB / 7.603GiB; nexadesk-load-backend-1 535.43% 546.2MiB / 7.603GiB; nexadesk-load-caddy-1 36.56% 80.89MiB / 7.603GiB; nexadesk-load-grafana-1 1.44% 135.5MiB / 7.603GiB; nexadesk-load-prometheus-1 0.00% 37.72MiB / 7.603GiB; nexadesk-load-redis-1 0.73% 7.016MiB / 7.603GiB; nexadesk-load-postgres-1 63.99% 347MiB / 7.603GiB; nexadesk-load-web-1 0.00% 10.23MiB / 7.603GiB; procurax-postgres 0.00% 55.29MiB / 7.603GiB; nexadesk-pg-test 0.00% 159.5MiB / 7.603GiB.
