"""Auditable research rules. Unknowns stay unknown; no invented forecasts."""
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from .metrics import finite

CHECKS = ['revenue','earnings','cash_flow','receivables','inventory','one_offs','dilution','sbc',
          'debt','interest','maturities','capex','leases','commitments','financing','competition','trend']
CHANNELS = ['revenue_orders','supply_production','commodity_transport','tariffs_sanctions','fx_funding']

def stamp(s):
    t=datetime.fromisoformat(s.replace('Z','+00:00'))
    if t.tzinfo is None: raise ValueError('时间戳缺少时区')
    return t

def sourced(item, cutoff):
    try:
        return (bool(item.get('source')) and urlsplit(item['url']).scheme in ('https','http')
                and stamp(item['published_at']) <= cutoff and stamp(item['fetched_at']) <= cutoff
                and item.get('verified') is True)
    except (KeyError,ValueError,TypeError): return False

def news_dedupe(items, cutoff, hours=24):
    groups=[]
    for n in sorted(items, key=lambda n:n.get('published_at',''),reverse=True):
        try:
            if stamp(n['published_at'])>cutoff or stamp(n['fetched_at'])>cutoff: continue
            u=urlsplit(n['url']); query=urlencode([(k,v) for k,v in parse_qsl(u.query) if not k.startswith('utm_') and k not in ('fbclid','gclid')]); canonical=urlunsplit((u.scheme,u.netloc,u.path,query,''))
            summary=n.get('summary','').strip()
            if not summary: continue # headline-only is not evidence
            n={**n,'canonical_url':canonical,'background':(cutoff-stamp(n['published_at'])).total_seconds()>hours*3600,
               'verification':'已核验' if sourced(n,cutoff) else '未核验', 'duplicates':[]}
            same=next((x for x in groups if x['canonical_url']==canonical or
                (n.get('event_id') and n.get('event_id')==x.get('event_id')) or
                SequenceMatcher(None,re.sub(r'\W','',summary.lower()),re.sub(r'\W','',x['summary'].lower())).ratio()>.88),None)
            if same is None: groups.append(n)
            else: same['duplicates'].append(n['url'])
        except (KeyError,ValueError,TypeError): continue
    return groups

def financial_valid(f, cutoff, max_age=200):
    reasons=[]
    if not sourced(f,cutoff): reasons.append('关键财务来源/披露时间未核验')
    try:
        age=(cutoff.date()-date.fromisoformat(f['period_end'])).days
        if age<0 or age>max_age: reasons.append('财务报告期过期或未来数据')
        if not f.get('version'): reasons.append('财务版本缺失')
    except (KeyError,ValueError): reasons.append('财务报告期缺失')
    if f.get('period_type') not in ('TTM','FY'):
        reasons.append('流量必须统一为TTM或FY口径')
    if f.get('currency')!='USD': reasons.append('财务币种非USD，需显式可追溯汇率转换')
    for k in ('revenue','net_income','operating_cash_flow','capex','cash','debt'):
        if not finite(f.get(k)): reasons.append('关键财务字段缺失:'+k)
    for k in ('revenue','capex','cash','debt'):
        if finite(f.get(k)) and f[k]<0: reasons.append('字段符号/单位错误:'+k)
    if f.get('severe_risk') is not False: reasons.append('严重财务风险未排除')
    return reasons

def valuation(stock, cutoff):
    f=stock['financials']; cap=stock['market_cap']; model=stock.get('business_model','unknown')
    v={'method':model,'metrics':{},'scenarios':None,'historical':None,'peers':None,'reverse':None,'missing':[]}
    if model in ('financial','reit','unknown'):
        v['missing'].append('金融/REIT/未知商业模式估值模块暂不覆盖'); return v
    ni=f['net_income']; ocf=f['operating_cash_flow']; capex=f['capex']; fcf=ocf-capex
    if model=='stable':
        v['metrics']['PE']=cap/ni if ni>0 and ni/cap>.001 else None
        v['metrics']['FCF_yield']=fcf/cap
        if finite(f.get('ebit')) and f['ebit']>0:
            v['metrics']['EV_EBIT']=(cap+f['debt']-f['cash'])/f['ebit']
    elif model=='growth':
        v['metrics']['FCF_yield']=fcf/cap
        v['metrics']['cash_runway_years']=f['cash']/(-fcf) if fcf<0 else None
    elif model=='cyclical':
        v['metrics']['FCF_yield']=fcf/cap
        v['missing'].append('需中周期盈利与供需成本验证，现期PE不直接估值')
    elif model=='conglomerate': v['missing'].append('分业务估值仅在可靠分部场景齐全时输出')
    assumptions=stock.get('valuation_evidence',{})
    for key in ('historical','peers'):
        e=assumptions.get(key,{})
        if sourced(e,cutoff) and e.get('comparability_explanation') and e.get('values'):
            v[key]=e
        else: v['missing'].append('缺少可比口径及解释:'+key)
    sc=dict(assumptions.get('scenarios',{}))
    if sourced(sc,cutoff) and sc.get('parameters'):
        from .scenarios import calculate
        try:
            for case in ('bear','base','bull'): sc[case]=calculate(model,sc['parameters'][case])
        except (KeyError,ValueError,TypeError,ZeroDivisionError):
            sc={}; v['missing'].append('场景模型参数不完整/不适用')
    # Values are USD COMPANY equity values, not ADR per-share values; never confuse share classes.
    if sourced(sc,cutoff) and sc.get('assumptions') and all(finite(sc.get(k)) and sc[k]>0 for k in ('bear','base','bull')) and sc['bear']<=sc['base']<=sc['bull']:
        v['scenarios']={**sc,'price_to_base_value':cap/sc['base'], 'horizon':'长期情景，不是三周目标价'}
    else: v['missing'].append('缺少可核验保守/基准/乐观假设')
    e=assumptions.get('forecast',{})
    if sourced(e,cutoff) and all(finite(e.get(k)) for k in ('revenue_next','discount_rate','terminal_growth')) and e['revenue_next']>0 and e['discount_rate']>e['terminal_growth']:
        # Constant perpetuity only, explicit simplified reverse valuation.
        ev=cap+f['debt']-f['cash']
        v['reverse']={'implied_steady_fcf_margin':ev*(e['discount_rate']-e['terminal_growth'])/e['revenue_next'],
                      'assumption':'恒定永续企业自由现金流简化模型，不代表预测','source':e}
    return v

def analyze(stock, m, cutoff, cfg):
    f=stock['financials']; quality={}
    for k in CHECKS:
        e=f.get('checks',{}).get(k,{})
        quality[k]=e if sourced(e,cutoff) and e.get('status') in ('pass','risk','unknown') else {'status':'unknown','note':'待核验'}
    v=valuation(stock,cutoff); ev=stock.get('event',{}); channels=ev.get('channels',{})
    evidence_ok=sourced(ev,cutoff) and (cutoff-stamp(ev['published_at'])).days<=cfg['evidence_age_days']
    complete=evidence_ok and all(sourced(channels.get(k,{}),cutoff) for k in CHANNELS)
    classification=ev.get('classification','D') if complete else 'D'
    if classification not in ('A','B','C','D'): classification='D'
    if classification=='B' and not (finite(ev.get('estimated_loss_fraction')) and 0<=ev['estimated_loss_fraction']<=1 and ev.get('loss_assumptions')):
        classification='D'
    news=news_dedupe(stock.get('news',[]),cutoff,cfg['news_age_hours'])
    verified_quality=sum(x.get('status')=='pass' for x in quality.values())
    unknown=[k for k,x in quality.items() if x.get('status')=='unknown']
    if v['scenarios'] and v['historical'] and v['peers']:
        val='有吸引力' if v['scenarios']['bear']>stock['market_cap'] else '情景未显示保守折价'
    else: val='证据不足'
    stable='初步企稳' if not m['new_low'] and (m['reclaimed'] or m['selling_decay']) else '未确认'
    qualified=val=='有吸引力' and classification in ('A','B') and not unknown and verified_quality>=14
    missing=v['missing']+(['事件传导链证据不足'] if classification=='D' else [])+(['质量核验缺项:'+','.join(unknown)] if unknown else [])
    risks=[x.get('note','财务风险') for x in quality.values() if x.get('status')=='risk']
    if risks: qualified=False
    # Core evidence dominates; volatility or drawdown cannot dominate ranking.
    score=verified_quality/len(CHECKS)*40+(25 if val=='有吸引力' else 0)+(20 if classification in ('A','B') else 0)+(10 if stable=='初步企稳' else 0)+(5 if any(n['verification']=='已核验' for n in news) else 0)
    return {'status':'合格' if qualified else '观察','valuation':v,'quality':quality,'news':news,
            'news_status':stock.get('news_status','unavailable'),'event_class':classification,
            'dimensions':{'估值吸引力':val,'事件实际损伤':classification,'价格企稳程度':stable},
            'financial_diagnostics':diagnostics(f),'score':score,'missing':missing,'counterevidence':risks+[ev.get('counterevidence','未知经营损伤；超额下跌不能证明错杀')],
            'event':ev,'exposures':stock.get('exposures',['风险暴露未核验'])}

def compact(parts, fallback, limit=100):
    """Select complete sentences; never cut a sentence or untrusted model text."""
    text=''.join(parts)
    if count(text)<=limit: return text
    if count(fallback)>limit: raise ValueError('模板本身超过字数限制')
    return fallback

def count(s): return len(re.sub(r'\s','',s))

def body(r):
    d=r['research']['dimensions']; m=r['metrics']; f=r['stock']['financials']
    rationale='交易活跃，近期回撤进入观察。' if m['drawdown20']<-.03 else '交易活跃、振幅达标，观察事件后表现。'
    cash=f'经营现金流{f["operating_cash_flow"]/1e8:.1f}亿美元；'
    evidence='估值'+d['估值吸引力']+'。'
    price='事件'+d['事件实际损伤']+'类，'+d['价格企稳程度']+'。'
    risk='风险：'+('继续创新低。' if m['new_low'] else '经营损伤仍须持续核验。')
    if r['research']['status']=='观察':
        missing=r['research']['missing']
        risk='缺项：'+('估值比较或情景证据。' if any('historical' in x or 'peers' in x or '假设' in x for x in missing) else '事件或财务质量证据。')
    primary=compact([rationale,cash,evidence,price,risk],cash+evidence+price+risk)
    from .llm import select_summary
    alternative=compact([cash,price,evidence,risk],primary)
    return select_summary([primary,alternative],{'dimensions':d})


def diagnostics(f):
    revenue=f['revenue']; ni=f['net_income']; ocf=f['operating_cash_flow']; capex=f['capex']
    out={'flow_basis':f.get('period_type'),'cash_conversion':ocf/ni if ni>0 else None,
         'free_cash_flow':ocf-capex,'capex_coverage':ocf/capex if capex>0 else None,
         'net_debt':f['debt']-f['cash'],'net_margin':ni/revenue if revenue>0 else None,
         'note':'高资本开支不直接判差；结合项目回报与融资承受力'}
    if finite(f.get('interest_expense')) and f['interest_expense']>0 and finite(f.get('ebit')):
        out['interest_coverage']=f['ebit']/f['interest_expense']
    prior=f.get('prior_comparable',{})
    for k in ('revenue','receivables','inventory','diluted_shares'):
        if finite(f.get(k)) and finite(prior.get(k)) and prior[k]>0:
            out[k+'_growth']=f[k]/prior[k]-1
    return out
