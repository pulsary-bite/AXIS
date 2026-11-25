# AXIS 0.6 — paper ML research
Public source code; no real orders, exchange keys, personal information or account access. The 50 USDT balance is fictitious. The worker uses only Bybit public closed-candle history; historical candle replay is not exchange execution.
 
Run tests: `python3 -m unittest -v`. Local cycle: `python3 worker.py --once`.
 
GitHub Actions performs CI and an optional paper cycle on main. For privacy, the hosted job does not persist account state or trading logs in the public repository. State storage must be configured separately before continuous paper trading. Scheduled runs currently perform a public market feed health check only; do not interpret these as continuous trading.
 
Do not commit credentials, database files or state exports. No profit guarantee.