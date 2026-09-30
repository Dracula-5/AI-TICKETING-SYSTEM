# Load test — same fixes, API_WORKERS=4, pool 10+10 per process (100k tickets)

Local, single machine (Intel64 Family 6 Model 186 Stepping 3, GenuineIntel; Docker VM 12 CPUs, 7.6 GiB), production compose stack behind Caddy, load generator on the same machine. SYNTHETIC load-test organization with 100000 tickets. Steady state 120 s per step after ramp-up. git `80f1e0d4a1`. SLO: p95 < 500 ms per endpoint group, < 1% errors.

| Users | Requests/s | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Within SLO | Slowest group (p95) |
|---|---|---|---|---|---|---|---|
| 250 | 64.5 | 100 | 2200 | 3800 | 0.01% | no | POST /tickets (7800 ms) |
| 500 | 83.3 | 120 | 13000 | 34000 | 41.22% | no | GET /kb/search (27000 ms) |

## Endpoint groups at 500 users

| Endpoint | Requests | Req/s | p50 | p95 | p99 | Failures |
|---|---|---|---|---|---|---|
| GET /kb/search | 401 | 3.1 | 10 | 27000 | 43000 | 308 |
| POST /tickets | 209 | 1.6 | 9 | 23000 | 60000 | 158 |
| GET /tickets (requester) | 1888 | 14.7 | 130 | 20000 | 43000 | 748 |
| POST /tickets/{id}/comments | 200 | 1.6 | 220 | 20000 | 28000 | 78 |
| GET /analytics/ai-performance | 93 | 0.7 | 210 | 18000 | 60000 | 40 |
| GET /tickets (queue) | 639 | 5.0 | 140 | 18000 | 34000 | 246 |
| GET /tickets?q= (search) | 218 | 1.7 | 190 | 18000 | 26000 | 84 |
| GET /tickets/{id} | 1830 | 14.2 | 130 | 17000 | 36000 | 771 |
| GET /tickets (my work) | 648 | 5.0 | 130 | 16000 | 34000 | 272 |
| GET /tickets (SLA at risk) | 223 | 1.7 | 150 | 15000 | 31000 | 78 |
| GET /analytics/overview | 306 | 2.4 | 99 | 11000 | 27000 | 124 |
| GET /kb/search (429 per-IP limit, expected) | 391 | 3.0 | 190 | 5200 | 16000 | 0 |
| POST /tickets (429 per-IP limit, expected) | 187 | 1.5 | 190 | 4800 | 24000 | 0 |
| GET /tickets/{id}/comments | 1828 | 14.2 | 110 | 2500 | 23000 | 777 |
| GET /tickets/{id}/history | 820 | 6.4 | 95 | 1800 | 17000 | 360 |
| GET /tickets/{id}/ai | 822 | 6.4 | 76 | 1400 | 10000 | 368 |

Container CPU / memory half-way through the last step: nexadesk-load-backend-1 7.79% 1.079GiB / 7.603GiB; nexadesk-load-worker-1 4.60% 229.1MiB / 7.603GiB; nexadesk-load-caddy-1 15.78% 100.1MiB / 7.603GiB; nexadesk-load-grafana-1 2.38% 135.6MiB / 7.603GiB; nexadesk-load-prometheus-1 0.00% 36.21MiB / 7.603GiB; nexadesk-load-redis-1 1.37% 7.047MiB / 7.603GiB; nexadesk-load-postgres-1 0.99% 356.3MiB / 7.603GiB; nexadesk-load-web-1 8.60% 10.04MiB / 7.603GiB; procurax-postgres 0.00% 55.17MiB / 7.603GiB; nexadesk-pg-test 0.00% 159.5MiB / 7.603GiB.
