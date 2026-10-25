from copy import deepcopy
import pytest
from equitybot.providers import HTTP,MassiveProvider,FileProvider
from equitybot.engine import run
from equitybot.research import stamp,valuation,analyze
from equitybot.metrics import metrics

def test_http_cache_and_retry(tmp_path,cfg,monkeypatch):
    cfg['http_rpm']=1000000; calls=[]
    class R:
        status_code=200
        text='{"x":1}'
        def json(self): return {'x':1}
    def get(*a,**kw): calls.append(kw); return R()
    monkeypatch.setattr('equitybot.providers.requests.get',get)
    h=HTTP(tmp_path,cfg)
    for _ in range(2): assert h.get('https://api.example/data',{'api_key':'TOPSECRET'})=={'x':1}
    assert len(calls)==1
    assert all('TOPSECRET' not in p.read_text() for p in (tmp_path/'cache').iterdir())

def test_no_secret_cross_domain(tmp_path,cfg,monkeypatch):
    monkeypatch.setenv('MASSIVE_API_KEY','secret')
    p=MassiveProvider(tmp_path,cfg)
    with pytest.raises(ValueError): p.api('https://attacker.invalid/next')

def test_missing_valuation_no_fabrication(raw,cfg,store):
    for s in raw['stocks']: s['valuation_evidence']={}; s['event']={}
    r=run(raw,cfg,store)
    assert len(r['final'])==10
    assert all(x['research']['status']=='观察' for x in r['final'])
    assert all(x['research']['event_class']=='D' for x in r['final'])
    assert all(x['research']['valuation']['scenarios'] is None for x in r['final'])

def test_valid_adr_not_whitelisted(raw,cfg,store):
    raw['stocks']=raw['stocks'][:10]
    s=raw['stocks'][0]; s['type']='ADRC'; s['symbol']='VIST'
    s['adr_evidence']={**s['cap_source'],'ordinary_shares_per_adr':1,'note':'fixture only'}
    r=run(raw,cfg,store); assert 'VIST' in [x['stock']['symbol'] for x in r['pool']]
    s['market_cap']=1e9
    r=run(raw,cfg,store); assert 'VIST' not in [x['stock']['symbol'] for x in r['pool']]

def test_event_c_never_qualified(raw,cfg,store):
    for s in raw['stocks']: s['event']['classification']='C'
    r=run(raw,cfg,store)
    assert all(x['research']['status']=='观察' for x in r['final'])

def test_future_scenario_not_used(raw):
    s=raw['stocks'][0]; s['valuation_evidence']['scenarios']['published_at']='2030-01-01T00:00:00Z'
    assert valuation(s,stamp(raw['cutoff']))['scenarios'] is None

def test_no_fabricated_reverse_valuation(raw):
    assert valuation(raw['stocks'][0],stamp(raw['cutoff']))['reverse'] is None

def test_scenario_calculations():
    from equitybot.scenarios import calculate
    assert calculate('stable',{'normalized_net_income':1e9,'justified_pe':20})==20e9
    a={'fcff':[100,110],'discount_rate':.1,'terminal_growth':.02,'cash':20,'debt':30,'other_claims':0}
    assert calculate('growth',a)==pytest.approx(100/1.1+110/1.1**2+110*1.02/.08/1.1**2-10)
    with pytest.raises(ValueError): calculate('growth',{**a,'terminal_growth':.11})

def test_invalid_check_status_cannot_qualify(raw,cfg,store):
    for s in raw['stocks']: s['financials']['checks']['maturities']['status']='unvalidated'
    r=run(raw,cfg,store)
    assert all(x['research']['status']=='观察' for x in r['final'])
