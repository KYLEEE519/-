import sqlite3, json, hashlib
from pathlib import Path

def encode(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False)
def digest(x): return hashlib.sha256(encode(x).encode()).hexdigest()

class Store:
    def __init__(self, directory):
        self.root=Path(directory); self.root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'bot.sqlite', timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, day TEXT, mode TEXT, input_hash TEXT, config TEXT, payload TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS mail(id TEXT PRIMARY KEY, state TEXT, attempts INTEGER DEFAULT 0, error TEXT, updated TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS feedback(company TEXT PRIMARY KEY, preference TEXT, reason TEXT, updated TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS audit(run_id TEXT, symbol TEXT, payload TEXT, PRIMARY KEY(run_id,symbol));
        ''')
    def save(self, report, raw, cfg):
        self.db.execute('INSERT OR IGNORE INTO runs(id,day,mode,input_hash,config,payload) VALUES (?,?,?,?,?,?)',
            (report['id'],report['asof'],report['mode'],digest(raw),encode(cfg),encode(report)))
        self.db.commit()
        path=self.root/'snapshots'/report['id']; path.mkdir(parents=True,exist_ok=True)
        for name,obj in [('input',raw),('config',cfg),('report',report)]:
            p=path/(name+'.json')
            if not p.exists(): p.write_text(encode(obj),encoding='utf-8')
        return path
    def previous(self, day, mode):
        rows=self.db.execute('SELECT payload FROM runs WHERE day<? AND mode=? ORDER BY day DESC,created DESC',(day,mode)).fetchall()
        prev=set(); ever=set()
        for i,(s,) in enumerate(rows):
            syms={r['stock']['company_id'] for r in json.loads(s)['final']}
            if i==0: prev=syms
            ever|=syms
        return prev,ever
    def preferences(self): return {c:(p,r) for c,p,r in self.db.execute('SELECT company,preference,reason FROM feedback')}
    def feedback(self,company,preference,reason):
        if preference not in ('favorite','uninterested','neutral'): raise ValueError('未知反馈类型')
        self.db.execute('INSERT OR REPLACE INTO feedback(company,preference,reason) VALUES (?,?,?)',(company,preference,reason)); self.db.commit()
    def latest(self):
        row=self.db.execute('SELECT payload FROM runs ORDER BY created DESC,rowid DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else None
