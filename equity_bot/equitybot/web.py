import json
from html import escape
from flask import Flask, Response, abort
from .storage import Store
from .report import render,shell

def app(data):
    app=Flask(__name__)
    @app.after_request
    def security(response):
        response.headers['Content-Security-Policy']="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
        response.headers['X-Content-Type-Options']='nosniff'
        return response
    def latest():
        s=Store(data); r=s.latest(); s.db.close(); return r
    @app.get('/')
    def index():
        r=latest()
        return render(r,True)[1] if r else shell('尚无报告','<h1>尚无报告</h1><p>请先执行 python -m equitybot run --demo</p>')
    @app.get('/pool')
    def pool():
        r=latest()
        if not r: return index()
        rows=''
        for x in r['pool']:
            s=x['stock']; rows+='<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in [s['symbol'],s['name'],x['industry_key'],x['research']['status'],round(x['priority'],2),x['research']['dimensions']])+'</tr>'
        h='<a href="/">精选</a><h1>完整研究池 '+str(len(r['pool']))+'只</h1><p>排名仅表示研究优先级。'+('模拟数据' if r['mode']=='demo' else '')+'</p><table><tr><th>代码</th><th>公司</th><th>行业</th><th>状态</th><th>优先级</th><th>三维证据</th></tr>'+rows+'</table>'
        h+=''.join('<details><summary>'+escape(x['stock']['symbol'])+' 研究详情</summary><pre>'+escape(json.dumps(x,ensure_ascii=False,indent=2))+'</pre></details>' for x in r['pool'])
        return shell('研究池',h)
    @app.get('/rejected')
    def rejected():
        r=latest(); return shell('淘汰记录','<a href="/">精选</a><h1>全部淘汰原因</h1><pre>'+escape(json.dumps(r['rejected'] if r else [],ensure_ascii=False,indent=2))+'</pre>')
    @app.get('/history')
    def history():
        s=Store(data); rows=s.db.execute('SELECT id,day,mode FROM runs ORDER BY day DESC,created DESC').fetchall(); s.db.close()
        return shell('历史','<h1>不可变时点快照</h1>'+''.join(f'<p><a href="/run/{i}">{day} {mode} {i}</a></p>' for i,day,mode in rows))
    @app.get('/run/<id>')
    def run(id):
        s=Store(data); row=s.db.execute('SELECT payload FROM runs WHERE id=?',(id,)).fetchone(); s.db.close()
        if not row: abort(404)
        return render(json.loads(row[0]),True)[1]
    @app.get('/audit')
    def audit():
        s=Store(data); rows=s.db.execute('SELECT run_id,symbol,payload FROM audit').fetchall(); s.db.close()
        return shell('研究审计','<h1>前向模拟跟踪</h1><p>价格收益不含分红；无实际下单，非投资组合业绩。</p><pre>'+escape(json.dumps(rows,ensure_ascii=False,indent=2))+'</pre>')
    @app.get('/api/latest')
    def api(): return Response(json.dumps(latest(),ensure_ascii=False),mimetype='application/json')
    return app
