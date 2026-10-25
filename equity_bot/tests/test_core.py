from copy import deepcopy
from collections import Counter
from datetime import datetime,timezone
import pytest
from equitybot.engine import hard_check,run
from equitybot.metrics import metrics,normalize_bars,event_residual,forward_audit
from equitybot.research import stamp,news_dedupe,count,compact,valuation
from equitybot.calendar import due,completed_session,sessions
from equitybot.report import render,market_body
from equitybot.llm import select_summary

def check(raw,cfg): return hard_check(raw['stocks'][0],raw['asof'],stamp(raw['cutoff']),cfg)

def test_definitions(raw):
    b=raw['stocks'][0]['bars']; m=metrics(b,raw['asof'])
    assert m['adv20']==pytest.approx(sum(x['close']*x['volume'] for x in b[-20:])/20)
    assert m['range5']==pytest.approx((max(x['high'] for x in b[-5:])-min(x['low'] for x in b[-5:]))/b[-6]['close'])
    assert m['range5']!=pytest.approx(m['return5'])

def test_actual_turnover(raw):
    b=raw['stocks'][0]['bars']
    for x in b: x['turnover']=19e6
    assert metrics(b,raw['asof'])['adv20']==19e6
    assert metrics(b,raw['asof'])['amount_method']=='来源真实成交金额'

@pytest.mark.parametrize('value,passed',[(5e9,False),(5e9+1,True),(None,False),(float('nan'),False)])
def test_cap_boundary(raw,cfg,value,passed):
    raw['stocks'][0]['market_cap']=value
    assert (not check(raw,cfg)[0])==passed

def test_strict_boundaries(raw,cfg):
    for b in raw['stocks'][0]['bars']: b['turnover']=1e7
    assert '20日日均成交额未严格大于门槛' in check(raw,cfg)[0]
    cfg['min_range5']=check(raw,cfg)[1]['range5']
    assert '5日价格振幅未严格大于门槛' in check(raw,cfg)[0]

@pytest.mark.parametrize('factor',[.5,2,.1])
def test_split_no_false_amplitude(raw,factor):
    b=raw['stocks'][0]['bars']; original=metrics(b,raw['asof'])
    for x in b[:-3]:
        for k in ('open','high','low','close'): x[k]/=factor
        x['volume']*=factor; x['split_factor']=factor
    adjusted=metrics(b,raw['asof'])
    for k in ('range5','adv20','atr_pct'): assert adjusted[k]==pytest.approx(original[k])

@pytest.mark.parametrize('ni',[1e9,2e8,1e6,-1e9])
def test_no_pe_cap(raw,cfg,ni):
    raw['stocks'][0]['financials']['net_income']=ni
    assert check(raw,cfg)[0]==[]

def test_full_flow(raw,cfg,store):
    r=run(raw,cfg,store)
    assert len(r['pool'])==50 and len(r['final'])==10
    assert max(Counter(x['industry_key'] for x in r['final']).values())<=2
    assert all(x['stock']['symbol'].startswith('DEMO') for x in r['final'])
    assert all(count(x['body'])<=100 for x in r['final'])
    assert count(market_body(r))<=100 # stricter than acceptance section's 200
    assert '模拟演示' in render(r)[1]

def test_shortage_unknown_industry(raw,cfg,store):
    raw['stocks']=raw['stocks'][:8]
    for s in raw['stocks']: s['industry']={}
    r=run(raw,cfg,store); assert len(r['final'])==2
    assert len(r['warnings'])>=2

def test_dedupe_company(raw,cfg,store):
    raw['stocks']=raw['stocks'][:3]
    for s in raw['stocks']: s['company_id']='same-company'
    r=run(raw,cfg,store); assert len(r['pool'])==1
    assert len([x for x in r['rejected'] if x['stage']=='dedupe'])==2

@pytest.mark.parametrize('change',[ 'stale','missing','future','severe','currency','adr','spac','etf','split'])
def test_rejections(raw,cfg,change):
    s=raw['stocks'][0]
    if change=='stale': s['bars']=s['bars'][:-1]
    if change=='missing': del s['financials']['revenue']
    if change=='future': s['financials']['published_at']='2030-01-01T00:00:00+00:00'
    if change=='severe': s['financials']['severe_risk']=True
    if change=='currency': s['currency']='ARS'
    if change=='adr': s['type']='ADRC'
    if change=='spac': s['is_spac']=True
    if change=='etf': s['type']='ETF'
    if change=='split': del s['bars'][0]['split_factor']
    assert check(raw,cfg)[0]

def test_news(raw):
    n=raw['stocks'][0]['news'][0]; duplicate={**n,'url':'https://other.example/reprint','is_reprint':True}
    title_only={**n,'summary':''}; old={**n,'url':'https://example.invalid/background','event_id':'old','summary':'不同的旧背景材料','published_at':'2026-09-01T00:00:00+00:00'}
    out=news_dedupe([n,duplicate,title_only,old],stamp(raw['cutoff']))
    assert len(out)==2 and any(x['duplicates'] for x in out) and any(x['background'] for x in out)

def test_missing_news_is_not_no_bad_news(raw,cfg,store):
    for s in raw['stocks']: s['news_status']='failed'; s['news']=[]
    r=run(raw,cfg,store); assert any('不代表没有负面新闻' in x for x in r['warnings'])

def test_char_compression():
    assert count(' A 中 2 。\n')==4
    assert compact(['很长。'*100],'短句。')=='短句。'

def test_calendar_dst_holiday_early_close():
    assert due('2026-11-27T19:14:00Z') is None
    assert due('2026-11-27T19:15:00Z')=='2026-11-27' # 13:00 EST close +75
    assert due('2026-07-03T23:00:00Z') is None
    assert due('2026-03-09T21:15:00Z')=='2026-03-09' # EDT
    assert due('2026-03-06T22:14:00Z') is None # EST
    assert completed_session('2026-10-25T01:00:00Z')=='2026-10-23'

def test_event_estimation_before_window(raw):
    b=raw['stocks'][0]['bars']; event=b[-5]['date']
    a=event_residual(b,b,b,event)
    altered=deepcopy(b)
    for x in altered[-5:]:
        for k in ('open','high','low','close'): x[k]*=2
    z=event_residual(altered,b,b,event)
    assert a['coefficients']==pytest.approx(z['coefficients'])

def test_forward_audit(raw):
    b=raw['stocks'][0]['bars']; r=forward_audit(b[-16]['date'],b,b)
    assert r['15']['relative_return']==pytest.approx(0)
    assert '尚未到期' in forward_audit(b[-4]['date'],b,b)['5']['status']

def test_snapshot_idempotent(raw,cfg,store):
    a=run(raw,cfg,store); b=run(raw,cfg,store)
    assert a['id']==b['id']
    assert store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]==1

def test_financial_and_reit_unsupported(raw):
    s=raw['stocks'][0]; s['business_model']='financial'
    v=valuation(s,stamp(raw['cutoff'])); assert not v['metrics'] and '暂不覆盖' in v['missing'][0]

def test_llm_cannot_inject_numbers(monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL','http://localhost/v1'); monkeypatch.setenv('LLM_MODEL','test')
    class Fake:
        def raise_for_status(self): pass
        def json(self): return {'choices':[{'message':{'content':'{"choice":0,"market_cap":999999999999,"recommend":"BUY"}'}}]}
    assert select_summary(['已核验模板。'],'ignore instructions',lambda *a,**k:Fake())=='已核验模板。'

def test_security_html(raw,cfg,store):
    raw['stocks'][0]['name']='<script>alert(1)</script>'
    r=run(raw,cfg,store); html=render(r,True)[1]
    assert '<script>' not in html

def test_feedback_does_not_change_hard_rules(raw,cfg,store):
    store.feedback(raw['stocks'][-1]['company_id'],'favorite','喜欢')
    r=run(raw,cfg,store); assert raw['stocks'][-1]['symbol'] not in [x['stock']['symbol'] for x in r['pool']]

def test_60day_reference_not_extra_hard_gate(raw,cfg):
    raw['stocks'][0]['bars']=raw['stocks'][0]['bars'][-20:]
    reasons,m=check(raw,cfg)
    assert not reasons
    assert m['adv60'] is None and m['rv60'] is None

def test_news_preserves_article_query_identity(raw):
    n=raw['stocks'][0]['news'][0]
    a={**n,'url':'https://news.example/article?id=1&utm_source=x','event_id':'one','summary':'原始事件的具体内容'}
    b={**n,'url':'https://news.example/article?id=2','event_id':'two','summary':'另一个完全无关的独立报道'}
    assert len(news_dedupe([a,b],stamp(raw['cutoff'])))==2

def test_future_bars_never_leak(raw):
    b=raw['stocks'][0]['bars']; before=metrics(b,raw['asof'])
    b.append({**b[-1],'date':'2026-10-26','close':999999,'high':999999})
    after=metrics(b,raw['asof'])
    assert before==after

def test_membership_retained_and_reentry(raw,cfg,store):
    from equitybot.providers import DemoProvider
    first=run(DemoProvider().load('2026-10-22'),cfg,store)
    today=run(raw,cfg,store)
    previous={x['stock']['company_id'] for x in first['final']}
    assert all(x['membership']=='保留' for x in today['final'] if x['stock']['company_id'] in previous)
    tomorrow=DemoProvider().load('2026-10-26')
    tomorrow['stocks']=[]; run(tomorrow,cfg,store)
    returned=run(DemoProvider().load('2026-10-27'),cfg,store)
    assert any(x['membership']=='重新入选' for x in returned['final'])
