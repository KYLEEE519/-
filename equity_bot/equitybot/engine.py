from datetime import date
from collections import Counter
from .metrics import metrics, finite, event_residual, price_context
from .research import financial_valid, analyze, sourced, stamp, body
from .storage import digest

def hard_check(s, asof, cutoff, cfg):
    reasons=[]; m=None
    if s.get('type') not in ('CS','ADRC'): reasons.append('非普通股/可靠ADR')
    if s.get('exchange') not in cfg['allowed_exchanges']: reasons.append('非支持主要交易所')
    if s.get('is_spac') is not False: reasons.append('空白支票公司或身份未核验')
    if not s.get('company_id'): reasons.append('公司身份无法去重')
    if s.get('currency')!='USD' or s.get('market_cap_currency')!='USD': reasons.append('币种未规范化')
    if s.get('market_cap_scope')!='company': reasons.append('市值不是公司总市值')
    if not finite(s.get('market_cap')) or s['market_cap']<=cfg['min_market_cap']: reasons.append('总市值未严格大于门槛')
    if not sourced(s.get('cap_source',{}),cutoff): reasons.append('市值来源不可核验')
    try:
        age=(date.fromisoformat(asof)-date.fromisoformat(s['cap_asof'])).days
        if age<0 or age>cfg['cap_age_days']: reasons.append('市值过期/未来数据')
    except (ValueError,KeyError): reasons.append('市值日期缺失')
    if not sourced(s.get('price_source',{}),cutoff): reasons.append('行情来源不可核验')
    if s.get('type')=='ADRC' and (not sourced(s.get('adr_evidence',{}),cutoff) or not finite(s.get('adr_evidence',{}).get('ordinary_shares_per_adr')) or s['adr_evidence']['ordinary_shares_per_adr']<=0): reasons.append('ADR比例/证券单位未核验')
    try:
        m=metrics(s.get('bars',[]),asof,cfg['calendar'])
        if m['adv20']<=cfg['min_adv20']: reasons.append('20日日均成交额未严格大于门槛')
        if m['range5']<=cfg['min_range5']: reasons.append('5日价格振幅未严格大于门槛')
    except (ValueError,KeyError,IndexError,TypeError) as e: reasons.append('行情质量:'+str(e))
    reasons+=financial_valid(s.get('financials',{}),cutoff,cfg['financial_age_days'])
    return reasons,m

def industry(s,cfg):
    i=s.get('industry',{})
    if i.get('taxonomy')!=cfg['taxonomy'] or not i.get('code') or not i.get('source'):
        return 'UNKNOWN'
    return i['code']

def run(raw, cfg, store):
    cutoff=stamp(raw['cutoff']); asof=raw['asof']; rejected=[]; passed=[]
    if cutoff.date()<date.fromisoformat(asof): raise ValueError('cutoff早于行情日期')
    from .calendar import calendar
    if calendar(cfg['calendar']).session_close(asof).to_pydatetime()>cutoff: raise ValueError('尚未收盘')
    for s in raw['stocks']:
        reasons,m=hard_check(s,asof,cutoff,cfg)
        if reasons: rejected.append({'symbol':s.get('symbol','?'),'stage':'hard','reasons':reasons}); continue
        # No PE threshold; financially healthy cash conversion and supplied sourced evidence influence priority.
        f=s['financials']; preliminary=10+min(10,max(0,f['operating_cash_flow']/max(abs(f['net_income']),1)))
        preliminary+=5 if sourced(s.get('event',{}),cutoff) else 0
        preliminary+=5 if sourced(s.get('valuation_evidence',{}).get('scenarios',{}),cutoff) else 0
        passed.append({'stock':s,'metrics':m,'preliminary_score':preliminary,'industry_key':industry(s,cfg)})
    passed.sort(key=lambda r:(-r['preliminary_score'],r['stock']['symbol']))
    unique=[]; seen=set()
    for r in passed:
        cid=r['stock']['company_id']
        if cid in seen: rejected.append({'symbol':r['stock']['symbol'],'stage':'dedupe','reasons':['同公司多证券去重']})
        else: unique.append(r); seen.add(cid)
    pool=unique[:cfg['pool_size']]
    for r in unique[cfg['pool_size']:]: rejected.append({'symbol':r['stock']['symbol'],'stage':'rank','reasons':['硬性合格，粗筛排名超过研究池上限']})
    prefs=store.preferences()
    for r in pool:
        r['research']=analyze(r['stock'],r['metrics'],cutoff,cfg)
        s=r['stock']; event_date=s.get('event',{}).get('date')
        r['price_context']=price_context(s['bars'],raw.get('benchmark'),s.get('industry_bars'),event_date)
        r['relative_analysis']={'status':'缺少事件日期/市场/行业基准'}
        if event_date and raw.get('benchmark') and s.get('industry_bars'):
            r['relative_analysis']=event_residual(s['bars'],raw['benchmark'],s['industry_bars'],event_date)
        preference=prefs.get(s['company_id'],('neutral',''))
        r['feedback']={'preference':preference[0],'reason':preference[1]}
        r['priority']=r['research']['score']+({'favorite':2,'uninterested':-2}.get(preference[0],0))
    ordered=sorted(pool,key=lambda r:(r['research']['status']!='合格',-r['priority'],r['stock']['symbol']))
    final=[]; counts=Counter(); prev,ever=store.previous(asof,raw['mode'])
    for r in ordered:
        if len(final)>=cfg['final_size']: break
        if counts[r['industry_key']]>=cfg['industry_cap']: continue
        cid=r['stock']['company_id']; r['membership']='保留' if cid in prev else '重新入选' if cid in ever else '新增'
        r['body']=body(r); final.append(r); counts[r['industry_key']]+=1
    warnings=list(raw.get('warnings',[]))
    if raw.get('market',{}).get('missing'):
        warnings.append('市场分析缺项：'+'、'.join(raw['market']['missing']))
    if len(pool)<cfg['pool_size']: warnings.append(f'研究池仅{len(pool)}只，硬筛或数据覆盖不足；门槛未放宽。')
    if len(final)<cfg['final_size']: warnings.append(f'精选仅{len(final)}只，合格数量或行业约束不足。')
    if any(r['research']['news_status']!='ok' for r in final): warnings.append('部分新闻抓取失败/未配置，不代表没有负面新闻。')
    exposures=Counter(e for r in final for e in r['research']['exposures'])
    from pathlib import Path
    software=digest({p.name:p.read_text() for p in sorted(Path(__file__).parent.glob('*.py'))})
    prior_row=store.db.execute('SELECT payload FROM runs WHERE day<? AND mode=? ORDER BY day DESC,created DESC LIMIT 1',(asof,raw['mode'])).fetchone()
    import json
    prior_news=set()
    if prior_row:
        prior_news={n.get('event_id') or n['canonical_url'] for row in json.loads(prior_row[0])['pool'] for n in row['research']['news']}
    new_news={n.get('event_id') or n['canonical_url'] for row in pool for n in row['research']['news']}-prior_news
    report={'id':digest({'input':raw,'config':cfg,'feedback':prefs,'software':software})[:24], 'software_hash':software, 'asof':asof,'cutoff':raw['cutoff'],
        'mode':raw['mode'],'pool':pool,'final':final,'rejected':rejected,'warnings':warnings,
        'market':raw.get('market',{}),'exposures':dict(exposures),
        'quality':{'scanned':len(raw['stocks']),'hard_pass':len(passed),'unique_pass':len(unique),
        'pool_count':len(pool),'final_count':len(final),'industry_counts':dict(counts),
        'hard_compliance':1.0 if final else None,'verified_news':sum(n['verification']=='已核验' for r in final for n in r['research']['news']),
        'unknown_quality_checks':sum(x.get('status')=='unknown' for r in final for x in r['research']['quality'].values()),
        'new_unique_events':len(new_news),'novelty_note':'相对上次交易日报告的事件ID/原文URL变化，不代表事件重要性评分',
        'new_count':sum(r['membership']=='新增' for r in final)}}
    store.save(report,raw,cfg)
    return report
