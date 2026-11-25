"""AXIS 0.6 closed-candle paper simulator. No exchange orders."""
import argparse, json, math, sqlite3, time, urllib.request
import model
from datetime import datetime, timezone
from pathlib import Path

HOUR=3600000
CAPITAL,FEE,SLIP,STOP,TARGET,MAX_DD=50.,.001,.0005,.018,.036,.10

def fetch():
    now=int(time.time()*1000);end=now;all_rows={}
    for _ in range(3):
        url=f'https://api.bybit.com/v5/market/kline?category=spot&symbol=BTCUSDT&interval=60&limit=1000&end={end}'
        with urllib.request.urlopen(url,timeout=15) as r:j=json.load(r)
        if j.get('retCode')!=0:raise RuntimeError('Bybit rejected market request')
        rows=j['result']['list']
        if not rows:break
        for x in rows:
            t=int(x[0]);row=(t,*map(float,x[1:5]))
            if t+HOUR<=now:
                if t in all_rows and all_rows[t]!=row:raise ValueError('Conflicting candle')
                all_rows[t]=row
        end=min(int(x[0]) for x in rows)-1
        if len(rows)<1000:break
    return list(all_rows.values())

def validate(rows):
    a=sorted(rows)
    if len(a)<73:raise ValueError('Insufficient candles')
    for i,(t,o,h,l,c) in enumerate(a):
        if t%HOUR or not all(math.isfinite(x) for x in (o,h,l,c)) or not 0<l<=min(o,c)<=max(o,c)<=h:raise ValueError('Invalid OHLC')
        if i and t-a[i-1][0]!=HOUR:raise ValueError('Missing or duplicate candles')
    return a

def connect(path):
    db=sqlite3.connect(path,timeout=30,isolation_level=None)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,ts INTEGER NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL)')
    return db

def initial():
    return dict(version='0.6',cash=CAPITAL,equity=CAPITAL,peak=CAPITAL,dd=0.,last=None,pos=None,pending=False,halt=False,fees=0.,closed=0,wins=0,source='Bybit BTCUSDT 1h',last_run=None,last_error=None,ml=None,pending_mode=0,pending_probability=None)

def read(db):
    r=db.execute('SELECT payload FROM state WHERE id=1').fetchone()
    return json.loads(r[0]) if r else initial()

def write(db,s):
    db.execute('INSERT INTO state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(json.dumps(s,allow_nan=False),))

def event(db,t,kind,**payload):
    db.execute('INSERT INTO events(ts,kind,payload) VALUES(?,?,?)',(t,kind,json.dumps(payload,allow_nan=False)))

def ml_signal(a,i,s,db):
    t=a[i][0];m=s.get('ml')
    if m is None or t-m.get('trained_through',-24*HOUR)>=24*HOUR:
        m=model.train(a[:i+1]);m['trained_through']=t;s['ml']=m
        event(db,t,'ML_TRAIN',active=m['active'],reason=m['reason'],threshold=m.get('threshold'),train_n=m.get('train_n',0),holdout=m.get('holdout'))
    v,mode=model.features(a,i);s['pending_mode']=mode;s['pending_probability']=None
    if not m['active'] or not model.candidate(a,i,mode):return False
    p=model.prob(m['model'],v);s['pending_probability']=p
    event(db,t,'ML_DECISION',probability=p,threshold=m['threshold'],accepted=p>=m['threshold'],mode=mode)
    return p>=m['threshold']

def advance(db,rows,now=None):
    a=validate(rows);now=int(time.time()*1000) if now is None else now
    if a[-1][0]+HOUR>now:raise ValueError('Unclosed candle')
    if now-(a[-1][0]+HOUR)>2*HOUR:raise ValueError('Stale market feed')
    db.execute('BEGIN IMMEDIATE')
    try:
        s=read(db)
        if s.get('version')!='0.6':raise ValueError('Use a fresh DB for 0.6; previous strategy state is not migrated')
        last=s['last'];positions={x[0]:i for i,x in enumerate(a)}
        if last is None:
            i=len(a)-1;s['last']=a[i][0];s['pending']=ml_signal(a,i,s,db);event(db,s['last'],'START',cash=s['cash'])
        else:
            if last not in positions:raise ValueError('Cursor outside downloaded history; operator review required')
            for i in range(positions[last]+1,len(a)):
                if i<72:raise ValueError('Insufficient warmup')
                t,o,h,l,c=a[i]
                if s['pending'] and not s['pos'] and not s['halt']:
                    entry=o*(1+SLIP);budget=min(s['cash']*.95,s['equity']*(.005 if s.get('pending_mode')==2 else .01)/(STOP+2*FEE+2*SLIP))
                    if budget>=5:
                        q=budget/(entry*(1+FEE));s['cash']-=budget;s['fees']+=q*entry*FEE;s['pos']=dict(q=q,entry=entry,cost=budget,stop=entry*(1-STOP),target=entry*(1+TARGET),age=0)
                        event(db,t,'PAPER_ENTRY',entry=entry,budget=budget,mode=s.get('pending_mode'),probability=s.get('pending_probability'))
                s['pending']=False
                p=s['pos'];px=None;why=None
                if p:
                    p['age']+=1
                    if l<=p['stop']:px=min(o,p['stop']);why='STOP'
                    elif h>=p['target']:px=p['target'];why='TARGET'
                    elif p['age']>=12:px=c;why='TIME'
                    mark=s['cash']+p['q']*c*(1-SLIP)*(1-FEE)
                    if px is None and 1-mark/s['peak']>=MAX_DD:px=c;why='DRAWDOWN'
                    if px is not None:
                        fill=px*(1-SLIP);fee=p['q']*fill*FEE;net=p['q']*fill-fee;pnl=net-p['cost'];s['cash']+=net;s['fees']+=fee;s['closed']+=1;s['wins']+=int(pnl>0);s['pos']=None
                        event(db,t,'PAPER_EXIT',exit=fill,pnl=pnl,why=why)
                p=s['pos'];s['equity']=s['cash']+(p['q']*c*(1-SLIP)*(1-FEE) if p else 0)
                s['peak']=max(s['peak'],s['equity']);s['dd']=max(s['dd'],1-s['equity']/s['peak'])
                if s['dd']>=MAX_DD and not s['halt']:s['halt']=True;event(db,t,'HALT',drawdown=s['dd'])
                if not s['pos'] and not s['halt']:s['pending']=ml_signal(a,i,s,db)
                s['last']=t;event(db,t,'MARK',equity=s['equity'])
        s['last_run']=datetime.now(timezone.utc).isoformat();s['last_error']=None;write(db,s);db.execute('COMMIT');return s
    except BaseException:
        db.execute('ROLLBACK');raise

def tick(db):
    try:return advance(db,fetch())
    except Exception as exc:
        db.execute('BEGIN IMMEDIATE')
        try:
            s=read(db);s['last_error']=str(exc)[:240];s['last_run']=datetime.now(timezone.utc).isoformat();write(db,s);db.execute('COMMIT')
        except BaseException:db.execute('ROLLBACK');raise
        raise

def export(db,path):
    s=read(db);s['events']=[dict(ts=t,kind=k,**json.loads(p)) for t,k,p in db.execute('SELECT ts,kind,payload FROM events ORDER BY id DESC LIMIT 100')];s['paper_only']=True;s['execution']='closed_candle_replay';s['ml']={k:v for k,v in (s.get('ml') or {}).items() if k!='model'}
    path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(path)

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',default='axis06.sqlite');p.add_argument('--once',action='store_true');p.add_argument('--export',default='status.json');p.add_argument('--interval',type=int,default=300);args=p.parse_args();db=connect(args.db)
    while True:
        try:tick(db);code=0
        except Exception as e:print('DATA ERROR:',e,flush=True);code=1
        export(db,args.export)
        if args.once:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.close();raise SystemExit(code)
        time.sleep(max(60,args.interval))
if __name__=='__main__':main()
