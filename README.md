# AXIS 0.6.1 — paper research
No live orders. No credentials or account data. Virtual capital only.
 
Default independent market source: Coinbase BTC-USD 1h. It is NOT Bybit BTCUSDT and is used for research only. Bybit remains an explicit optional source where permitted; no automatic cross-venue mixing or bypass. Separate databases are mandatory per venue.
 
Run: python3 -m unittest -v. Local paper cycle: python3 worker.py --once. Set AXIS_FEED=bybit only in an authorized environment.
 
GitHub Actions tests and attempts one ephemeral in-memory research cycle hourly. No trade journal or database is published; this is not continuous paper trading. Private persistent storage and authorized Bybit connectivity are still needed. No profit guarantee.
