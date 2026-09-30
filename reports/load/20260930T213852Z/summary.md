# Load test — after P11 fixes: async session teardown, dashboard cache, trigram search, model warm-up (100k tickets, API_WORKERS=2)

Local, single machine (Intel64 Family 6 Model 186 Stepping 3, GenuineIntel; Docker VM 12 CPUs, 7.6 GiB), production compose stack behind Caddy, load generator on the same machine. SYNTHETIC load-test organization with 100000 tickets. Steady state 120 s per step after ramp-up. git `80f1e0d4a1`. SLO: p95 < 500 ms per endpoint group, < 1% errors.

| Users | Requests/s | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Within SLO | Slowest group (p95) |
|---|---|---|---|---|---|---|---|
| 50 | 14.6 | 59 | 120 | 190 | 0.00% | no | GET /analytics/overview (500 ms) |
| 100 | 29.6 | 62 | 150 | 290 | 0.03% | yes | GET /analytics/overview (450 ms) |
| 250 | 65.6 | 320 | 970 | 1400 | 0.00% | no | POST /tickets (2000 ms) |
| 500 | 37.5 | 6 | 43000 | 55000 | 91.34% | no | GET /analytics/overview (46000 ms) |

## Endpoint groups at 500 users

| Endpoint | Requests | Req/s | p50 | p95 | p99 | Failures |
|---|---|---|---|---|---|---|
| GET /analytics/overview | 194 | 1.5 | 8 | 46000 | 55000 | 179 |
| GET /kb/search | 495 | 3.9 | 7 | 46000 | 61000 | 466 |
| GET /tickets (my work) | 467 | 3.7 | 7 | 46000 | 56000 | 417 |
| GET /tickets (requester) | 1261 | 9.9 | 7 | 46000 | 56000 | 1128 |
| POST /tickets | 222 | 1.7 | 7 | 46000 | 54000 | 209 |
| GET /analytics/ai-performance | 64 | 0.5 | 7 | 45000 | 56000 | 58 |
| GET /tickets/{id} | 427 | 3.3 | 7 | 45000 | 55000 | 391 |
| GET /tickets (queue) | 440 | 3.4 | 6 | 43000 | 60000 | 389 |
| GET /tickets?q= (search) | 128 | 1.0 | 7 | 43000 | 60000 | 119 |
| GET /tickets (SLA at risk) | 107 | 0.8 | 6 | 36000 | 52000 | 95 |
| POST /tickets/{id}/comments | 61 | 0.5 | 7 | 36000 | 47000 | 58 |
| GET /kb/search (429 per-IP limit, expected) | 13 | 0.1 | 5200 | 14000 | 14000 | 0 |
| POST /tickets (429 per-IP limit, expected) | 7 | 0.1 | 1800 | 12000 | 12000 | 0 |
| GET /tickets/{id}/comments | 424 | 3.3 | 5 | 9900 | 43000 | 400 |
| GET /tickets/{id}/history | 240 | 1.9 | 5 | 270 | 43000 | 231 |
| GET /tickets/{id}/ai | 241 | 1.9 | 5 | 16 | 1600 | 236 |

Container CPU / memory half-way through the last step: nexadesk-load-backend-1 1.65% 595.1MiB / 7.603GiB; nexadesk-load-worker-1 0.04% 228.2MiB / 7.603GiB; nexadesk-load-caddy-1 28.38% 78.49MiB / 7.603GiB; nexadesk-load-grafana-1 2.94% 135.6MiB / 7.603GiB; nexadesk-load-prometheus-1 0.00% 35.77MiB / 7.603GiB; nexadesk-load-redis-1 1.43% 6.816MiB / 7.603GiB; nexadesk-load-postgres-1 0.63% 305.5MiB / 7.603GiB; nexadesk-load-web-1 0.00% 9.809MiB / 7.603GiB; procurax-postgres 6.15% 57.12MiB / 7.603GiB; nexadesk-pg-test 0.00% 159.7MiB / 7.603GiB.
