"""R1 Regression Guard: prevent legacy metric imports in production code.

Any production metric code importing from src.coordinate.metric_crs
for area, buffer, distance, snapping, or topology will fail this test.

Design Note §9: Geographic Search Approximation only.
"""