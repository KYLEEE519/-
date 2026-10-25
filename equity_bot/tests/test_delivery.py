import pytest
from equitybot.engine import run
from equitybot.mail import deliver
from equitybot.web import app

class SMTP:
    calls=0
    def __init__(self,*a,**k): pass
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def ehlo(self): pass
    def starttls(self,**k): pass
    def login(self,*a): pass
    def send_message(self,msg): SMTP.calls+=1; return {}

def setup(monkeypatch,raw,cfg,store):
    raw['mode']='live' # test-only transport fixture, no actual network
    for k,v in {'MAIL_SEND_ENABLED':'true','SMTP_HOST':'mock','SMTP_FROM':'a@example.invalid','SMTP_TO':'b@example.invalid'}.items(): monkeypatch.setenv(k,v)
    return run(raw,cfg,store)

def test_preview_default(raw,cfg,store):
    r=run(raw,cfg,store); assert deliver(r,store)=='preview'
    assert store.db.execute('SELECT COUNT(*) FROM mail').fetchone()[0]==0

def test_no_demo_send(raw,cfg,store,monkeypatch):
    monkeypatch.setenv('MAIL_SEND_ENABLED','true')
    with pytest.raises(ValueError): deliver(run(raw,cfg,store),store,True,SMTP)

def test_mail_dedup(raw,cfg,store,monkeypatch):
    SMTP.calls=0; r=setup(monkeypatch,raw,cfg,store)
    assert deliver(r,store,True,SMTP)=='sent'
    r['id']='revised'
    assert deliver(r,store,True,SMTP)=='duplicate-or-unknown'
    assert SMTP.calls==1

def test_safe_failure_retry(raw,cfg,store,monkeypatch):
    r=setup(monkeypatch,raw,cfg,store)
    class Fail(SMTP):
        def starttls(self,**k): raise TimeoutError('secret must not be logged')
    assert deliver(r,store,True,Fail)=='failed'
    assert deliver(r,store,True,SMTP)=='sent'
    assert 'secret' not in str(store.db.execute('SELECT * FROM mail').fetchall())

def test_ambiguous_failure_not_retried(raw,cfg,store,monkeypatch):
    r=setup(monkeypatch,raw,cfg,store)
    class Fail(SMTP):
        def send_message(self,msg): raise TimeoutError()
    assert deliver(r,store,True,Fail)=='unknown'
    assert deliver(r,store,True,SMTP)=='duplicate-or-unknown'

def test_ui(raw,cfg,store):
    run(raw,cfg,store); client=app(str(store.root)).test_client()
    for path in ('/','/pool','/rejected','/history','/audit','/api/latest'):
        response=client.get(path)
        assert response.status_code==200
        assert 'Content-Security-Policy' in response.headers
