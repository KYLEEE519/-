"""Reproducible fixture generation; all securities and future prices are synthetic."""
from pathlib import Path
import json,math
from equitybot.providers import DemoProvider
from equitybot.storage import Store
from equitybot.engine import run
from equitybot.mail import deliver
from equitybot.web import app
from equitybot.calendar import calendar

root=Path(__file__).resolve().parents[1]
cfg=json.loads((root/'config.json').read_text())
raw=DemoProvider().load('2026-10-23')
examples=root/'examples'; examples.mkdir(exist_ok=True)
(examples/'input_demo.json').write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
store=Store(root/'demo_validation_data')
r=run(raw,cfg,store); deliver(r,store)
source=store.root/'reports'/r['id']
for file in ('email.html','email.eml'):
    (examples/('demo_'+file)).write_bytes((source/file).read_bytes())
client=app(str(store.root)).test_client()
for route,name in [('/','index.html'),('/pool','pool.html'),('/rejected','rejected.html'),('/history','history.html')]:
    text=client.get(route).get_data(as_text=True)
    for old,new in [('href="/"','href="index.html"'),('href="/pool"','href="pool.html"'),('href="/rejected"','href="rejected.html"'),('href="/history"','href="history.html"'),('href="/audit"','href="audit.html"')]: text=text.replace(old,new)
    if name=='history.html':
        from equitybot.report import shell
        text=shell('演示历史','<h1>单次演示快照</h1><p>'+r['id']+'</p><a href="index.html">打开该演示</a><p>完整历史版本请运行本地服务查看。</p>')
    (examples/name).write_text(text,encoding='utf-8')
cal=calendar(); idx=cal.sessions.get_loc(cal.date_to_session(raw['asof']))
days=[d.date().isoformat() for d in cal.sessions[idx+1:idx+16]]
future={}
for row in r['pool']:
    s=row['stock']; b=[dict(x) for x in s['bars']]; anchor=b[-1]['close']
    for i,d in enumerate(days):
        p=anchor*(1+.003*i+.015*math.sin(i))
        b.append({'date':d,'open':p*.997,'high':p*1.015,'low':p*.985,'close':p,'volume':1e6,'split_factor':1})
    future[s['symbol']]=b
payload={'mode':'demo','prices':future,'benchmark':next(iter(future.values())),'note':'未来行情也是合成数据，非真实后验表现'}
(examples/'forward_demo.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
(examples/'run_summary.json').write_text(json.dumps({'id':r['id'],'quality':r['quality'],'warnings':r['warnings']},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'pool':len(r['pool']),'final':len(r['final']),'rejected':len(r['rejected']),'mode':r['mode']}))
