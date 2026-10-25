import math
import numpy as np
from .calendar import sessions

def finite(x):
    return isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)

def normalize_bars(bars):
    """Raw OHLC * cumulative split factor; raw volume / factor. Never dividend-adjust here."""
    out = []
    for b in sorted(bars, key=lambda b: b['date']):
        f = b.get('split_factor')
        if not finite(f) or f <= 0:
            raise ValueError('拆股因子缺失或无效')
        vals = [b.get(k) for k in ('open','high','low','close','volume')]
        if not all(finite(x) and x > 0 for x in vals):
            raise ValueError('OHLCV 无效')
        if b['low'] > min(b['open'], b['close']) or b['high'] < max(b['open'], b['close']) or b['low'] > b['high']:
            raise ValueError('OHLC 关系错误')
        amount = b.get('turnover')
        if amount is not None and (not finite(amount) or amount <= 0):
            raise ValueError('成交金额无效')
        out.append({**b, **{k:b[k]*f for k in ('open','high','low','close')},
                    'volume':b['volume']/f,
                    'amount':amount if amount is not None else b['close']*b['volume'],
                    'approx': amount is None})
    return out

def metrics(bars, asof, cal='XNYS'):
    b = normalize_bars([x for x in bars if x['date'] <= asof])
    if len({x['date'] for x in b}) != len(b):
        raise ValueError('重复交易日')
    expected = sessions(asof, 20, cal)
    if [x['date'] for x in b[-20:]] != expected:
        raise ValueError('最近20个完整交易日缺失/行情过期')
    c = np.array([x['close'] for x in b]); a = np.array([x['amount'] for x in b])
    r = np.diff(np.log(c)); tr = [max(x['high']-x['low'],abs(x['high']-p),abs(x['low']-p)) for x,p in zip(b[1:],c[:-1])]
    return dict(price=float(c[-1]), adv20=float(a[-20:].mean()), median20=float(np.median(a[-20:])),
                adv60=float(a[-60:].mean()) if len(a)>=60 else None, relative_amount=float(a[-1]/a[-20:].mean()),
                range5=(max(x['high'] for x in b[-5:])-min(x['low'] for x in b[-5:]))/c[-6],
                atr_pct=float(np.mean(tr[-14:])/c[-1]), rv20=float(np.std(r[-20:],ddof=1)*np.sqrt(252)) if len(r)>=20 else None,
                rv60=float(np.std(r[-60:],ddof=1)*np.sqrt(252)) if len(r)>=60 else None, drawdown20=float(c[-1]/max(c[-20:])-1),
                return5=float(c[-1]/c[-6]-1), return20=float(c[-1]/c[-21]-1) if len(c)>=21 else None,
                new_low=bool(b[-1]['low'] < min(x['low'] for x in b[-6:-1])),
                reclaimed=bool(c[-1]>min(x['low'] for x in b[-6:-1]) and b[-1]['low']<min(x['low'] for x in b[-6:-1])),
                selling_decay=bool(c[-1]<c[-2] and a[-1]<np.mean(a[-6:-1])),
                amount_method='close×volume近似（含混合日）' if any(x['approx'] for x in b[-20:]) else '来源真实成交金额',
                activity60_days=sum(x['amount']>10_000_000 for x in b[-60:]) if len(b)>=60 else None, asof=asof)

def event_residual(stock, market, industry, event_date):
    """OLS alpha + market + industry, coefficients estimated strictly BEFORE event."""
    maps=[{x['date']:x['close'] for x in normalize_bars(b)} for b in (stock,market,industry)]
    days=sorted(set(maps[0]) & set(maps[1]) & set(maps[2]))
    if len(days)<70: return {'status':'不足70个共同交易日'}
    prices=np.array([[m[d] for m in maps] for d in days]); ret=prices[1:]/prices[:-1]-1
    pre=np.array([d<event_date for d in days[1:]])
    if pre.sum()<60 or (~pre).sum()==0: return {'status':'事件前样本不足或事件未发生'}
    x=np.column_stack([np.ones(len(ret)),ret[:,1:]])
    coef=np.linalg.lstsq(x[pre][-120:],ret[pre,0][-120:],rcond=None)[0]
    return {'status':'调查线索，非错杀证明','pre_event_samples':min(120,int(pre.sum())),
            'coefficients':coef.tolist(),'cumulative_residual':float((ret[~pre,0]-x[~pre]@coef).sum())}

def forward_audit(entry, future, benchmark, horizons=(5,10,15)):
    """Forward-only price return; dividends excluded, no pretend portfolio P&L."""
    b=normalize_bars(future); bm={x['date']:x for x in normalize_bars(benchmark)}
    anchor=next((x for x in b if x['date']==entry),None)
    if anchor is None or entry not in bm: return {'status':'缺少同拆股基准入选日价格'}
    result={}
    for h in horizons:
        from .calendar import calendar
        cal=calendar(); start=cal.sessions.get_loc(cal.date_to_session(entry))
        expected=[x.date().isoformat() for x in cal.sessions[start+1:start+h+1]]
        w=[x for x in b if x['date'] in expected]
        if [x['date'] for x in w]!=expected or any(d not in bm for d in expected):
            result[str(h)]={'status':'尚未到期或缺失交易日'}; continue
        p=anchor['close']; ret=w[-1]['close']/p-1
        result[str(h)]={'price_return':ret,'relative_return':ret-(bm[w[-1]['date']]['close']/bm[entry]['close']-1),
                        'mfe':max(x['high'] for x in w)/p-1,'mae':min(x['low'] for x in w)/p-1,
                        'status':'价格收益，不含分红；研究审计非交易业绩'}
    return result

def price_context(stock, benchmark=None, industry=None, event_date=None):
    """Describe price-only behavior, no claims about investor identity."""
    s=normalize_bars(stock); result={}
    for name,other in [('market',benchmark),('industry',industry)]:
        if not other: result[name]={'status':'基准缺失'}; continue
        bm={x['date']:x for x in normalize_bars(other)}
        joint=[x for x in s if x['date'] in bm]
        if len(joint)<21: result[name]={'status':'共同样本不足'}; continue
        w=joint[-21:]; sr=w[-1]['close']/w[0]['close']-1
        br=bm[w[-1]['date']]['close']/bm[w[0]['date']]['close']-1
        down=[]
        for a,b in zip(w[-6:-1],w[-5:]):
            if bm[b['date']]['close']<bm[a['date']]['close']:
                down.append(b['close']/a['close']-1-(bm[b['date']]['close']/bm[a['date']]['close']-1))
        result[name]={'relative_return20':sr-br,'down_market_days5':len(down),
                      'mean_excess_on_down_days':float(np.mean(down)) if down else None,
                      'return_basis':'拆股调整价格收益，不含分红'}
    if event_date:
        w=[x for x in s if x['date']>=event_date]
        result['post_event_new_low']=(w[-1]['low']<min(x['low'] for x in w[:-1])) if len(w)>1 else None
    return result
