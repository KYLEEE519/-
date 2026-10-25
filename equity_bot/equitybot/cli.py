import argparse, json, os, time
from datetime import datetime, timezone
from pathlib import Path
from .calendar import completed_session,due
from .storage import Store,encode
from .providers import DemoProvider,FileProvider,MassiveProvider
from .engine import run
from .mail import deliver

def config():
    c=json.loads(Path(os.environ.get('BOT_CONFIG','config.json')).read_text())
    if not 60<=c['close_delay_minutes']<=90: raise ValueError('收盘延迟必须60—90分钟')
    if c['pool_size']>50 or c['final_size']>10 or c['industry_cap']>2: raise ValueError('不得超过50/10/行业2上限')
    if min(c['pool_size'],c['final_size'],c['industry_cap'])<1: raise ValueError('数量必须正数')
    return c

def execute(args,asof=None):
    cfg=config(); store=Store(os.environ.get('BOT_DATA','data'))
    mode='demo' if args.demo else os.environ.get('BOT_PROVIDER','demo')
    day=asof or args.asof or completed_session()
    provider=DemoProvider() if mode=='demo' else FileProvider(os.environ.get('BOT_INPUT','input.json')) if mode=='file' else MassiveProvider(store.root,cfg) if mode=='massive' else None
    if provider is None: raise ValueError('未知数据源')
    raw=provider.load(day)
    report=run(raw,cfg,store)
    status=deliver(report,store,args.send)
    for _ in range(2):
        if status!='failed': break
        time.sleep(2)
        status=deliver(report,store,args.send)
    print(encode({'id':report['id'],'mode':report['mode'],'asof':day,'pool':len(report['pool']),'final':len(report['final']),
                  'mail':status,'report':str(store.root/'reports'/report['id']/'email.html'),'warnings':report['warnings']}))
    store.db.close(); return report

def audit(args):
    from .metrics import forward_audit
    s=Store(os.environ.get('BOT_DATA','data')); raw=json.loads(Path(args.file).read_text())
    for rid,payload in s.db.execute('SELECT id,payload FROM runs').fetchall():
        r=json.loads(payload)
        if raw.get('mode')!=r['mode']: continue
        for row in r['pool']:
            sym=row['stock']['symbol']
            if sym not in raw.get('prices',{}): continue
            result=forward_audit(r['asof'],raw['prices'][sym],raw.get('benchmark',[]))
            s.db.execute('INSERT OR REPLACE INTO audit VALUES (?,?,?)',(rid,sym,encode(result)))
    s.db.commit(); s.db.close(); print('前向审计已更新；没有改变任何历史筛选快照')

def load_env():
    p=Path('.env')
    if p.exists():
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line: continue
            k,v=line.split('=',1); k=k.strip(); v=v.strip()
            if k.replace('_','').isalnum(): os.environ.setdefault(k,v.strip('\"').strip("'"))

def main():
    load_env()
    p=argparse.ArgumentParser(description='本地美股研究Bot，无交易接口')
    sub=p.add_subparsers(dest='cmd',required=True)
    for name in ('run','schedule'):
        q=sub.add_parser(name); q.add_argument('--demo',action='store_true'); q.add_argument('--asof'); q.add_argument('--send',action='store_true')
    q=sub.add_parser('serve'); q.add_argument('--host',default='127.0.0.1'); q.add_argument('--port',type=int,default=8080)
    q=sub.add_parser('preview'); q.add_argument('--output',default='preview.html')
    q=sub.add_parser('feedback'); q.add_argument('company'); q.add_argument('preference',choices=['favorite','uninterested','neutral']); q.add_argument('--reason',default='')
    q=sub.add_parser('audit'); q.add_argument('file')
    args=p.parse_args()
    try:
        if args.cmd=='run': execute(args)
        elif args.cmd=='serve':
            from .web import app
            app(os.environ.get('BOT_DATA','data')).run(host=args.host,port=args.port,debug=False)
        elif args.cmd=='preview':
            from .report import render
            s=Store(os.environ.get('BOT_DATA','data')); r=s.latest()
            if not r: raise ValueError('先运行run')
            Path(args.output).write_text(render(r)[1],encoding='utf-8'); print(args.output)
        elif args.cmd=='feedback':
            Store(os.environ.get('BOT_DATA','data')).feedback(args.company,args.preference,args.reason); print('反馈已保存，只影响软排序±2分')
        elif args.cmd=='audit': audit(args)
        elif args.cmd=='schedule':
            cfg=config(); seen=None
            while True:
                day=due(datetime.now(timezone.utc),cfg['close_delay_minutes'],cfg['calendar'])
                if day and day!=seen:
                    try:
                        execute(args,day); seen=day
                    except Exception as e: print('本次失败，60秒后重试：'+type(e).__name__,flush=True)
                time.sleep(60)
    except (ValueError,RuntimeError,FileNotFoundError) as e:
        p.exit(2,'运行失败：'+str(e)+'\n')
