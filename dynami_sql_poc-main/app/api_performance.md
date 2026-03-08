# API Performance Test Comparison Summary

## Test Run 1 - Pinot API Performance

**Test Duration:** 75 seconds  
**Tool:** SoapUI 5.7.2

### Test Configuration

- **Concurrent Users:** 10
- **Total Requests:** 150
- **Environment:** Local machine testing Pinot-backed REST endpoint
- **Test Type:** Baseline performance assessment

### Key Results

| Metric | Value |
|--------|-------|
| Throughput | 1.99 requests/second |
| Average Response Time | 4.46 seconds |
| Minimum Response Time | 0.50 seconds |
| Maximum Response Time | 11.98 seconds |
| Error Rate | 0% |
| Total Data Transfer | 601,980 bytes (~0.60 MB) |
| Average Response Size | ~4.0 KB |

---

## Test Run 2 - Trino API Performance

**Test Duration:** 6 minutes 48 seconds  
**Tool:** SoapUI 5.7.2

### Test Configuration

- **Concurrent Users:** 10
- **Total Requests:** 150
- **Environment:** Local machine testing Trino-backed REST endpoint
- **Test Type:** Follow-up comparison run

### Key Results

| Metric | Value |
|--------|-------|
| Throughput | 0.36 requests/second |
| Average Response Time | 24.13 seconds |
| Minimum Response Time | 2.93 seconds |
| Maximum Response Time | 59.76 seconds |
| Error Rate | 1.3% (2 errors) |
| Total Data Transfer | 386,292 bytes (~0.37 MB) |
| Average Response Size | ~2.6 KB |

---

## Performance Comparison

| Metric | Pinot (Aug 30) | Trino (Sep 2) | Change |
|--------|----------------|---------------|--------|
| Throughput | 1.99 req/s | 0.36 req/s | -82% |
| Avg Response Time | 4.46s | 24.13s | +441% |
| Max Response Time | 11.98s | 59.76s | +399% |
| Error Rate | 0% | 1.3% | +1.3% |

## Summary

The second test run showed significantly degraded performance compared to the baseline, with 5x slower response times and 5x lower throughput. Two socket/timeout errors occurred during the test period, indicating potential stability issues under load.

## Environment Notes

- Tests conducted on local environment
- Results are preliminary and reflect local machine performance
- Production environment performance may differ due to network and infrastructure variations