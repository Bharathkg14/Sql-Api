# Pinot API Performance Test Summary


**Test Duration:** 75 seconds
**Tool:** SoapUI 5.7.2

## Test Configuration

- **Concurrent Users:** 10
- **Total Requests:** 150
- **Environment:** Local machine testing Pinot-backed REST endpoint
- **Test Type:** Baseline performance assessment

## Key Results

| Metric | Value |
|--------|-------|
| Throughput | 1.99 requests/second |
| Average Response Time | 4.46 seconds |
| Minimum Response Time | 0.50 seconds |
| Maximum Response Time | 11.98 seconds |
| Error Rate | 0% |
| Total Data Transfer | 601,980 bytes (~0.60 MB) |
| Average Response Size | ~4.0 KB |

## Summary

The API demonstrated functional stability with zero errors during the test period. However, response times showed high variability with some requests taking nearly 12 seconds to complete. The service sustained approximately 2 requests per second under the 10-user concurrent load.

## Environment Notes

- Test conducted on local environment
- Results are preliminary and reflect local machine performance
- Production environment performance may differ due to network and infrastructure variations