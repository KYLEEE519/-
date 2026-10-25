from html import escape
from urllib.parse import urlsplit
import json
from .research import count, compact

STYLE='''body{font:15px/1.65 system-ui,sans-serif;color:#20334a;background:#f3f6fa;margin:0}main{max-width:1150px;margin:auto;padding:30px}h1{font-size:28px}h2{margin-top:28px}article,.panel{background:white;border:1px solid #dce5ee;border-radius:12px;padding:18px;margin:14px 0}.tag{color:#087b78;font-weight:700}.warning{background:#fff2d8;padding:14px;border-radius:8px}small,.muted{color:#52677f}a{color:#1769aa}table{border-collapse:collapse;width:100%;background:white}td,th{border-bottom:1px solid #dce5ee;padding:9px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}nav a{margin-right:22px}details{margin-top:12px}'''
def link(url,label):
    if urlsplit(str(url)).scheme not in ('http','https'): return escape(str(label))
    return '<a rel="noreferrer" href="'+escape(str(url),quote=True)+'">'+escape(str(label))+'</a>'
def shell(title,body): return f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{escape(title)}</title><style>{STYLE}</style><main>{body}</main></html>'
def pct(v): return f'{v:.1%}'
def valuation_line(r):
    v=r['research']['valuation']['metrics']; fields=[]
    for k in ('PE','FCF_yield','EV_EBIT'):
        if k in v: fields.append(k+':'+('不适用' if v[k] is None else pct(v[k]) if k=='FCF_yield' else f'{v[k]:.1f}'))
    return ' / '.join(fields) or '估值暂不覆盖'
def market_body(r):
    return compact([r['market'].get('summary','市场情绪、地缘政策及银行流动性数据缺失，无法判断。')],
                   '市场情绪及恐慌见指标；地缘政策影响待核验；银行流动性见日期与缺项，暂不作确定结论。')
def render(r,detail=False):
    demo=r['mode']=='demo'; n=len(r['final']); title=f'美股观察简报｜{r["asof"]}｜{n}只候选'
    h=f'<h1>{escape(title)}</h1>'
    if demo: h+='<p class="warning"><b>模拟演示</b>：全部公司、数据和研究结论均为虚构，不是真实股票推荐。</p>'
    if detail: h+='<nav><a href="/">精选</a><a href="/pool">研究池</a><a href="/rejected">淘汰记录</a><a href="/history">历史</a><a href="/audit">研究审计</a></nav>'
    summary=market_body(r); assert count(summary)<=100
    h+='<h2>市场摘要</h2><p>'+escape(summary)+'</p><small>'
    h+=' ｜ '.join(escape(f'{x["name"]} {x["value"]} {x["unit"]}（{x["date"]}）'+(' [陈旧]' if x.get('stale') else '')) for x in r['market'].get('indicators',[]))+'</small><p>'
    h+=' · '.join(link(x['url'],x['name']) for x in r['market'].get('indicators',[])[:4])+'</p>'
    for row in r['final']:
        s=row['stock']; m=row['metrics']; re=row['research']; text=row['body']; assert count(text)<=100
        h+='<article><b>'+escape(f'{s["name"]}（{s["symbol"]}）｜{s.get("industry",{}).get("name") or "未知行业"}｜{re["status"]}｜{row["membership"]}')+'</b>'
        h+='<p class="muted">'+escape(f'${m["price"]:.2f}｜市值${s["market_cap"]/1e9:.2f}B｜ADV20 ${m["adv20"]/1e6:.1f}M｜5日振幅{pct(m["range5"])}｜{valuation_line(row)}｜{r["asof"]}')+'</p>'
        h+='<p>'+escape(text)+'</p><small>'+escape(m['amount_method'])+'</small><p>'
        sources=[s['financials'],s['cap_source']]+[x for x in re['news'][:2]]
        seen=set()
        for x in sources:
            if x['url'] not in seen: h+=link(x['url'],x.get('source','来源'))+' · '; seen.add(x['url'])
        h+='</p>'
        if detail:
            h+='<p class="tag">'+escape(' ｜ '.join(k+':'+v for k,v in re['dimensions'].items()))+'</p>'
            h+='<p>'+escape('板块：'+s.get('sector','未知')+'；共同风险：'+'、'.join(re['exposures']))+'</p>'
            h+='<p>尚缺证据：'+escape('；'.join(re['missing']) or '无已识别缺项，仍需复核')+'</p>'
            h+='<p>重要反证：'+escape('；'.join(re['counterevidence']))+'</p>'
            h+='<details><summary>完整指标、财务检查、事件传导、新闻及版本</summary><pre>'+escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre></details>'
        h+='</article>'
    if r['warnings']: h+='<h2>数据与运行说明</h2><ul>'+''.join('<li>'+escape(x)+'</li>' for x in r['warnings'])+'</ul>'
    if detail:
        h+='<div class="panel"><h2>市场完整分析 / 缺失项</h2><pre>'+escape(json.dumps(r['market'],ensure_ascii=False,indent=2))+'</pre><h2>共同风险暴露</h2><pre>'+escape(json.dumps(r['exposures'],ensure_ascii=False,indent=2))+'</pre></div>'
    return title,shell(title,h)
