"""Replaceable adapters. Live provider never silently falls back to synthetic data."""
from typing import Protocol
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, quote
import hashlib, json, os, time, math
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import requests
from .calendar import sessions
from .research import CHECKS, CHANNELS

class Provider(Protocol):
    def load(self, asof: str) -> dict: ...

class HTTP:
    def __init__(self, root, cfg):
        self.root=Path(root)/'cache'; self.root.mkdir(parents=True,exist_ok=True)
        self.cfg=cfg; self.last=0
    def get(self,url,params=None,headers=None,ttl=3600,text=False):
        # Credentials are sent only to the explicitly selected endpoint; never persisted/logged.
        safe={k:v for k,v in (params or {}).items() if k.lower() not in ('apikey','api_key','token')}
        key=hashlib.sha256((url+json.dumps(safe,sort_keys=True)).encode()).hexdigest()
        p=self.root/key
        if p.exists() and time.time()-p.stat().st_mtime<ttl:
            return p.read_text() if text else json.loads(p.read_text())
        for i in range(self.cfg['http_retries']):
            time.sleep(max(0,60/self.cfg['http_rpm']-(time.monotonic()-self.last)))
            self.last=time.monotonic()
            try:
                r=requests.get(url,params=params,headers=headers,timeout=self.cfg['http_timeout'],allow_redirects=False)
                if r.status_code in (429,500,502,503,504):
                    time.sleep(min(8,2**i)); continue
                if r.status_code!=200: raise RuntimeError(f'HTTP {r.status_code}，端点权限/来源不可用')
                value=r.text if text else r.json()
                tmp=p.with_suffix('.tmp'); tmp.write_text(r.text if text else json.dumps(value)); tmp.replace(p)
                return value
            except (requests.RequestException,ValueError):
                if i==self.cfg['http_retries']-1: raise RuntimeError('数据请求超时/格式错误') from None
        raise RuntimeError('重试耗尽')

class FileProvider:
    def __init__(self,path): self.path=path
    def load(self,asof):
        raw=json.loads(Path(self.path).read_text())
        if raw['asof']!=asof: raise ValueError('输入快照日期与运行交易日不一致')
        if raw['mode'] not in ('demo','live'): raise ValueError('输入模式必须demo/live')
        return raw

class DemoProvider:
    def load(self,asof):
        days=sessions(asof,150); cutoff=asof+'T22:00:00+00:00'
        def src(): return {'source':'SYNTHETIC FIXTURE','url':'https://example.invalid/synthetic','published_at':asof+'T20:00:00+00:00','fetched_at':cutoff,'verified':True}
        stocks=[]
        for i in range(76):
            bars=[]
            for j,d in enumerate(days):
                p=65+i*.9+math.sin(j*.45+i)*2.8-j*.015
                bars.append({'date':d,'open':p*.998,'high':p*1.018,'low':p*.982,'close':p,
                             'volume':900000+i*1000,'split_factor':1})
            f={**src(),'period_end':(datetime.fromisoformat(asof)-timedelta(days=65)).date().isoformat(),
               'version':'fixture-v1','period_type':'TTM','currency':'USD','revenue':8e9,'net_income':5e8,'operating_cash_flow':9e8,
               'capex':4e8,'cash':2e9,'debt':3e9,'ebit':7e8,'severe_risk':False,
               'checks':{k:{**src(),'status':'pass','note':'模拟核验项，非真实企业财务'} for k in CHECKS}}
            s={'symbol':f'DEMO{i:03}','name':f'模拟企业{i:03}','company_id':f'fictional-{i}',
               'type':'CS','exchange':'XNYS','is_spac':False,'currency':'USD','market_cap_currency':'USD',
               'market_cap_scope':'company','market_cap':8e9+i*1e8,'cap_asof':asof,'cap_source':src(),'price_source':src(),
               'industry':{'taxonomy':'SIC','code':str(1000+(i%12)*100),'name':f'模拟行业{i%12}','source':'SYNTHETIC SIC fixture'},
               'sector':f'模拟板块{i%4}','bars':bars,'financials':f,'business_model':'cyclical' if i%4==0 else 'stable',
               'exposures':['商品价格' if i%4==0 else '融资成本','全球风险偏好'],
               'valuation_evidence':{'historical':{**src(),'values':[10,12,14],'comparability_explanation':'模拟同口径，增长及利率变化假设不变'},
                 'peers':{**src(),'values':[12,15],'comparability_explanation':'模拟同商业模式、增长和风险'},
                 'scenarios':{**src(),'bear':18e9,'base':21e9,'bull':25e9,'assumptions':'仅模拟公司权益估值，不是实际目标价'}},
               'event':{**src(),'date':days[-5],'classification':'A','counterevidence':'模拟：未来商品价格变化可能形成真实损伤',
                        'channels':{k:{**src(),'impact':'未发现直接损伤（模拟）'} for k in CHANNELS}},
               'news_status':'ok','news':[{**src(),'title':'模拟事件','summary':'演示企业公告摘要，所有信息均为模拟。',
                       'entities':[f'DEMO{i:03}'],'is_reprint':False,'event_id':f'demo-{i}','kind':'fact'}]}
            if i>=65: s['market_cap']=3e9 # intentional rejection
            if i==64: s['financials']['severe_risk']=True
            if i==63: s['type']='ETF'
            stocks.append(s)
        return {'mode':'demo','asof':asof,'cutoff':cutoff,'stocks':stocks,'benchmark':stocks[0]['bars'],
            'market':{'summary':'模拟市场风险偏好偏弱，恐慌升温；模拟地缘事件待核验；银行流动性数据为演示值，不代表现实。',
                      'indicators':[{'name':'模拟VIX','value':25,'date':asof,'unit':'指数点','url':'https://example.invalid/synthetic'},
                                    {'name':'模拟准备金','value':3000,'date':days[-3],'unit':'十亿美元','url':'https://example.invalid/synthetic'}],
                      'details':'全部为合成数据；市场宽度、政策、期限结构和银行融资压力不代表当前市场。'},
            'warnings':['演示模式：全部公司、行情、新闻、财务及估值均为合成数据，不构成真实股票推荐。']}

class MassiveProvider:
    def __init__(self, root, cfg):
        self.http=HTTP(root,cfg); self.cfg=cfg; self.root=Path(root)
        self.key=os.environ.get('MASSIVE_API_KEY')
        if not self.key: raise ValueError('缺少MASSIVE_API_KEY；请显式使用demo模式')
    def api(self,path,params=None,ttl=3600):
        url=path if path.startswith('https://') else 'https://api.massive.com'+path
        if urlsplit(url).hostname!='api.massive.com': raise ValueError('拒绝跨域分页凭据转发')
        return self.http.get(url,params,{'Authorization':'Bearer '+self.key},ttl)
    def bars(self,symbol,asof):
        start=(datetime.fromisoformat(asof)-timedelta(days=260)).date().isoformat()
        path=f'/v2/aggs/ticker/{quote(symbol,safe="")}/range/1/day/{start}/{asof}'
        raw=self.api(path,{'adjusted':'false','sort':'asc','limit':50000}).get('results',[])
        adj=self.api(path,{'adjusted':'true','sort':'asc','limit':50000}).get('results',[])
        adjusted={b['t']:b for b in adj}; out=[]
        for b in raw:
            if b['t'] not in adjusted: continue
            a=adjusted[b['t']]; factor=a['c']/b['c']
            # Verify all prices share the same split factor; do not mix adj close with raw high/low.
            if any(abs(a[k]/b[k]-factor)>1e-5 for k in ('o','h','l')): raise ValueError('拆股价格比例不一致')
            out.append({'date':datetime.fromtimestamp(b['t']/1000,timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date().isoformat(),
                        'open':b['o'],'high':b['h'],'low':b['l'],'close':b['c'],'volume':b['v'],'split_factor':factor})
        return out
    def universe(self,asof):
        page='/v3/reference/tickers'; params={'market':'stocks','locale':'us','active':'true','date':asof,'limit':1000}; out=[]
        while page:
            data=self.api(page,params,86400); out.extend(data.get('results',[])); page=data.get('next_url'); params=None
        return [s for s in out if s.get('type') in ('CS','ADRC') and s.get('primary_exchange') in self.cfg['allowed_exchanges']]
    def sec_raw(self,cik):
        ua=os.environ.get('SEC_USER_AGENT','')
        if not ua or '@' not in ua: return 'SEC_USER_AGENT未配置'
        url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json'
        data=self.http.get(url,headers={'User-Agent':ua,'Accept-Encoding':'gzip, deflate'},ttl=21600)
        p=self.root/'sec'; p.mkdir(exist_ok=True)
        # Content-hash filenames preserve revisions; raw XBRL does NOT imply normalized financial verification.
        encoded=json.dumps(data); version=hashlib.sha256(encoded.encode()).hexdigest()[:16]
        (p/f'{cik}-{version}.json').write_text(encoded)
        return {'url':url,'version':version,'fetched_at':datetime.now(timezone.utc).isoformat()}
    def load(self,asof):
        from .calendar import completed_session
        if asof!=completed_session(): raise ValueError('实时适配器只允许最近完整交易日；历史请导入时点快照')
        evidence_path=Path(os.environ.get('BOT_EVIDENCE','evidence.json'))
        overlay=json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
        symbols=self.universe(asof); total=len(symbols)
        if self.cfg['max_symbols']: symbols=symbols[:self.cfg['max_symbols']]
        out=[]; warnings=[]
        for item in symbols:
            symbol=item['ticker']
            try:
                d=self.api('/v3/reference/tickers/'+quote(symbol,safe=''),{'date':asof},21600)['results']
                fetched=datetime.now(timezone.utc).isoformat()
                source={'source':'Massive','url':'https://api.massive.com/v3/reference/tickers/'+quote(symbol,safe='')+'?date='+asof,
                        'published_at':asof+'T00:00:00+00:00','fetched_at':fetched,'verified':True}
                # provider market_cap is company-level; never reconstruct from ADR price × ordinary shares.
                s={'symbol':symbol,'name':d.get('name',symbol),'company_id':d.get('cik'),
                   'type':d.get('type'),'exchange':d.get('primary_exchange'),'currency':d.get('currency_name','').upper(),
                   'market_cap':d.get('market_cap'),'market_cap_currency':'USD','market_cap_scope':'company',
                   'cap_asof':asof,'cap_source':source,'price_source':{**source,'url':'https://api.massive.com/v2/aggs/ticker/'+quote(symbol,safe='')+'/range/1/day/'+(datetime.fromisoformat(asof)-timedelta(days=260)).date().isoformat()+'/'+asof+'?adjusted=false','basis':'原始OHLCV与拆股调整OHLC对照；价格收益不含分红'},'is_spac':None,
                   'industry':{'taxonomy':'SIC','code':d.get('sic_code'),'name':d.get('sic_description'),'source':'Massive/SEC SIC'},
                   'sector':d.get('sic_description','未知'),'bars':[],'financials':{},'news_status':'unavailable'}
                # Only allow explicitly documented evidence fields, never symbol/price/cap overrides.
                allowed=('is_spac','financials','business_model','exposures','valuation_evidence','event','adr_evidence','industry_bars','news','news_aliases')
                s.update({k:v for k,v in overlay.get(symbol,{}).items() if k in allowed})
                if isinstance(s['market_cap'],(float,int)) and s['market_cap']>self.cfg['min_market_cap']:
                    s['bars']=self.bars(symbol,asof)
                    if d.get('cik'):
                        try: s['sec_raw']=self.sec_raw(d['cik'])
                        except Exception: s['sec_raw']='SEC请求失败'
                out.append(s)
            except Exception as e:
                warnings.append(f'{symbol}数据获取失败：{type(e).__name__}')
                out.append({'symbol':symbol}) # retain failures in reject ledger
        news,status=fetch_rss(self.http)
        for s in out:
            s['news_status']=status
            # Entity matching must be supplied/verified; substring ticker matching is unsafe.
            existing=s.get('news',[])
            aliases=[s.get('name','')]+s.get('news_aliases',[])
            matched=[]
            for n in news:
                text=(n['title']+' '+n['summary']).lower()
                if any(len(a)>=5 and a.lower() in text for a in aliases):
                    matched.append({**n,'entities':[s['symbol']],'entity_match':'公司名称/人工别名匹配，未独立核验'})
            s['news']=existing+matched
        market=fetch_market(self.http,asof)
        benchmark=[]
        try: benchmark=self.bars('SPY',asof)
        except Exception: warnings.append('大盘基准SPY获取失败')
        from .metrics import normalize_bars
        daily=[]
        for s in out:
            try:
                b=normalize_bars(s.get('bars',[]))
                if len(b)>=2 and b[-1]['date']==asof: daily.append(b[-1]['close']/b[-2]['close']-1)
            except ValueError: pass
        market['breadth']={'advancers':sum(x>0 for x in daily),'decliners':sum(x<0 for x in daily),'unchanged':sum(x==0 for x in daily),'coverage':len(daily),'scope':'已成功获取行情的市值初筛子样本，非全市场宽度','date':asof}
        if len(benchmark)>=2:
            b=normalize_bars(benchmark)
            market['indicators'].insert(0,{'name':'SPY日价格收益','value':round((b[-1]['close']/b[-2]['close']-1)*100,2),'date':b[-1]['date'],'unit':'%（不含分红）','url':'https://massive.com/docs/rest/stocks/aggregates/custom-bars'})
        market['news']=news
        if len(symbols)<total: warnings.append(f'覆盖受max_symbols限制：{len(symbols)}/{total}，不是全市场扫描')
        warnings.append('财务、SPAC/ADR和估值证据需evidence.json核验覆盖；SEC原始XBRL不会自动视为已核验。')
        return {'mode':'live','asof':asof,'cutoff':datetime.now(timezone.utc).isoformat(),'stocks':out,'benchmark':benchmark,'market':market,'warnings':warnings}

def fetch_rss(http):
    feeds=[x.strip() for x in os.environ.get('NEWS_RSS_URLS','').split(',') if x.strip()]; result=[]; failures=0
    for url in feeds:
        try:
            if urlsplit(url).scheme!='https': raise ValueError('RSS必须HTTPS')
            root=ET.fromstring(http.get(url,text=True,ttl=900))
            for item in root.findall('.//item'):
                desc=item.findtext('description',''); pub=item.findtext('pubDate','')
                if not desc or not pub: continue
                import re
                result.append({'source':urlsplit(url).hostname,'url':item.findtext('link',''),
                    'title':item.findtext('title',''),'summary':re.sub('<[^>]+>','',desc),
                    'published_at':parsedate_to_datetime(pub).isoformat(),'fetched_at':datetime.now(timezone.utc).isoformat(),
                    'entities':[],'is_reprint':None,'verified':False,'kind':'media_report'})
        except Exception: failures+=1
    return result, 'unavailable' if not feeds else 'partial' if failures else 'ok'

def fetch_market(http,asof):
    key=os.environ.get('FRED_API_KEY'); indicators=[]; missing=[]
    series={'VIXCLS':('VIX','指数点',5),'BAMLH0A0HYM2':('高收益信用利差','百分点',5),
            'WRESBAL':('银行准备金','百万美元',14),'SOFR':('SOFR','%',5),'IORB':('准备金利率','%',5),
            'RRPONTSYD':('隔夜逆回购','十亿美元',5),'WLCFLPCL':('贴现窗口一级信贷','百万美元',14)}
    for sid,(name,unit,age) in series.items():
        if not key: missing.append(name); continue
        try:
            data=http.get('https://api.stlouisfed.org/fred/series/observations',params={'api_key':key,'file_type':'json',
                'series_id':sid,'observation_end':asof,'realtime_start':asof,'realtime_end':asof,'sort_order':'desc','limit':10})
            rows=[x for x in data['observations'] if x['value']!='.']
            x=rows[0]; stale=(datetime.fromisoformat(asof)-datetime.fromisoformat(x['date'])).days>age
            indicators.append({'name':name,'value':float(x['value']),'date':x['date'],'unit':unit,'stale':stale,
                'change':float(x['value'])-float(rows[1]['value']) if len(rows)>1 else None,
                'url':'https://fred.stlouisfed.org/series/'+sid})
        except Exception: missing.append(name)
    by={x['name']:x for x in indicators}
    if 'SOFR' in by and '准备金利率' in by and by['SOFR']['date']==by['准备金利率']['date']:
        indicators.append({'name':'SOFR-IORB','value':by['SOFR']['value']-by['准备金利率']['value'],
                           'date':by['SOFR']['date'],'unit':'百分点','url':by['SOFR']['url']})
    v=by.get('VIX',{})
    mood='恐慌数据缺失或陈旧' if not v or v.get('stale') else ('VIX偏高' if v['value']>=25 else 'VIX未达25观察线')
    return {'summary':mood+'；地缘政策影响待核验；银行流动性需结合准备金与融资利差，不能由降息推断。',
            'indicators':indicators,'missing':missing+['全市场宽度','VIX期限结构','地缘政策独立核验'],
            'details':'不计算不完整的复合情绪分数。VIX阈值25仅描述水平，不是经校准预测；SOFR-IORB不是政策目标利差。准备金/贴现窗口为周度，逐项显示日期。RSS失败不代表无风险。'}
