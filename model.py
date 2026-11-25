"""Causal logistic filter for paper trades; standard library only."""
import math
H=12
W=72
FEE=.001
SLIP=.0005
THRESHOLDS=(.45,.5,.55,.6,.65,.7)

def avg(a,i,n):return sum(a[j][4] for j in range(i-n+1,i+1))/n

def features(a,i):
    c=a[i][4]; f=avg(a,i,12); s=avg(a,i,50); d=f/s-1; slope=s/avg(a,i-12,50)-1
    ret=[math.log(a[j][4]/a[j-1][4]) for j in range(i-23,i+1)]; mu=sum(ret)/24
    vol=math.sqrt(sum((r-mu)**2 for r in ret)/24)
    atr=sum(max(a[j][2]-a[j][3],abs(a[j][2]-a[j-1][4]),abs(a[j][3]-a[j-1][4]))/a[j-1][4] for j in range(i-23,i+1))/24
    hi=max(x[2] for x in a[i-23:i+1]);lo=min(x[3] for x in a[i-23:i+1])
    mode=3 if vol>.012 or atr>.022 else 0 if d>.004 and slope>.001 else 1 if d<-.004 and slope<-.001 else 2
    return [d,slope,vol,atr,c/a[i-6][4]-1,c/a[i-24][4]-1,(c-lo)/max(hi-lo,1e-9),c/f-1,int(mode==0),int(mode==2)],mode

def candidate(a,i,mode):
    c=a[i][4]
    if mode==0:return c>max(x[2] for x in a[i-20:i]) or (avg(a,i,12)>avg(a,i,36) and avg(a,i-1,12)<=avg(a,i-1,36))
    if mode==2:return a[i-1][4]<avg(a,i-1,20)*.99 and c>a[i-1][4] and c>avg(a,i,50)*.96
    return False

def outcome(a,i,fee=FEE,slip=SLIP):
    entry=a[i+1][1]*(1+slip);stop=entry*.982;target=entry*1.036;end=i+H;exit=a[end][4]
    for j in range(i+1,end+1):
        _,o,h,l,c=a[j]
        if l<=stop:exit=min(o,stop);end=j;break
        if h>=target:exit=target;end=j;break
    return exit*(1-slip)*(1-fee)/(entry*(1+fee))-1,end

def samples(a,start,end):
    out=[]
    for i in range(max(start,W),end-H):
        v,m=features(a,i)
        if candidate(a,i,m):
            r,j=outcome(a,i);out.append((i,v,m,r,j))
    return out

def sigmoid(x):return 1/(1+math.exp(-max(-35,min(35,x))))

def fit(rows):
    n=len(rows)
    if n<35 or sum(x[3]>0 for x in rows)<5 or sum(x[3]<=0 for x in rows)<5:return None
    mean=[sum(x[1][j] for x in rows)/n for j in range(10)]
    sd=[max(1e-8,math.sqrt(sum((x[1][j]-mean[j])**2 for x in rows)/n)) for j in range(10)]
    z=[([max(-6,min(6,(x[1][j]-mean[j])/sd[j])) for j in range(10)],int(x[3]>0)) for x in rows];w=[0.]*10;b=0.
    for _ in range(180):
        g=[0.]*10;gb=0.
        for v,y in z:
            e=sigmoid(b+sum(x*t for x,t in zip(v,w)))-y;gb+=e
            for j in range(10):g[j]+=e*v[j]
        b-=.12*gb/n;w=[t-.12*(g[j]/n+.02*t) for j,t in enumerate(w)]
    return dict(w=w,b=b,mean=mean,sd=sd)

def prob(m,v):return sigmoid(m['b']+sum(w*max(-6,min(6,(x-u)/s)) for w,x,u,s in zip(m['w'],v,m['mean'],m['sd'])))

def score(rows,m=None,th=0,stress=False,a=None):
    cash=peak=50.;dd=0.;n=0;last=-1
    for i,v,mode,r,end in rows:
        if i<last or m is not None and prob(m,v)<th:continue
        if stress:r,end=outcome(a,i,FEE*2,SLIP*2)
        budget=min(cash*.95,cash*(.005 if mode==2 else .01)/(.018+2*FEE*(2 if stress else 1)+2*SLIP*(2 if stress else 1)))
        if budget<5:continue
        cash+=budget*r;last=end;n+=1;peak=max(peak,cash);dd=max(dd,1-cash/peak)
        if dd>=.10:break
    return dict(pnl=cash-50,n=n,dd=dd)

def train(a):
    if len(a)<600:return dict(active=False,reason='insufficient_history',train_n=0,threshold=None)
    c1=int(len(a)*.5);c2=int(len(a)*.75);tr=samples(a,W,c1);va=samples(a,c1,c2);te=samples(a,c2,len(a));m=fit(tr)
    info=dict(active=False,reason='insufficient_training',train_n=len(tr),valid_n=len(va),test_n=len(te),threshold=None,trained_through=a[-1][0])
    if not m:return info
    base=score(va);opts=[]
    for th in THRESHOLDS:
        r=score(va,m,th)
        if r['n']>=10 and r['pnl']>0 and r['pnl']>=base['pnl'] and r['dd']<.1:opts.append((r['pnl'],th))
    if not opts:return {**info,'reason':'validation_rejected'}
    th=max(opts,key=lambda x:(x[0],-x[1]))[1];r=score(te,m,th);b=score(te);stress=score(te,m,th,True,a)
    active=r['n']>=10 and r['pnl']>0 and r['pnl']>=b['pnl'] and stress['pnl']>0 and r['dd']<.1
    return {**info,'active':active,'reason':'admitted' if active else 'holdout_rejected','threshold':th,'model':m,'holdout':r,'baseline':b,'stress':stress}
