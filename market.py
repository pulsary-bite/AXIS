"""Independent public Coinbase BTC-USD research feed. No account access."""
import json,time,urllib.request,urllib.parse
from datetime import datetime,timezone
HOUR=3600000
SOURCE='Coinbase BTC-USD 1h'
def iso(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
def request(url):
    req=urllib.request.Request(url,headers={'User-Agent':'AXIS-research/0.6.1','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)
def fetch(now=None,count=3000,request_fn=request):
    now=int(time.time()*1000) if now is None else now
    if not 600<=count<=3000:raise ValueError('count out of range')
    end=now//HOUR*HOUR;start=end-count*HOUR;all_rows={}
    for lo in range(start,end,299*HOUR):
        hi=min(lo+299*HOUR,end)
        q=urllib.parse.urlencode({'start':iso(lo),'end':iso(hi),'granularity':3600})
        rows=request_fn('https://api.exchange.coinbase.com/products/BTC-USD/candles?'+q)
        if not isinstance(rows,list):raise ValueError('Invalid Coinbase response')
        for x in rows:
            if len(x)<6:raise ValueError('Invalid Coinbase candle')
            t=int(x[0])*1000
            if not lo<=t<hi:continue
            row=(t,float(x[3]),float(x[2]),float(x[1]),float(x[4]))
            if t in all_rows and all_rows[t]!=row:raise ValueError('Conflicting candles')
            all_rows[t]=row
    if len(all_rows)!=count or min(all_rows)!=start or max(all_rows)!=end-HOUR:raise ValueError('Incomplete Coinbase history; no interpolation')
    return sorted(all_rows.values())
