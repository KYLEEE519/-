"""Preview default. SMTP cannot promise exactly-once after ambiguous network failures."""
import os, smtplib, ssl, hashlib
from email.message import EmailMessage
from .report import render

def deliver(report,store,send=False,smtp_factory=None):
    title,html=render(report)
    path=store.root/'reports'/report['id']; path.mkdir(parents=True,exist_ok=True)
    (path/'email.html').write_text(html,encoding='utf-8')
    msg=EmailMessage(); msg['Subject']=('[模拟] ' if report['mode']=='demo' else '')+title
    msg['From']=os.environ.get('SMTP_FROM','preview@example.invalid'); msg['To']=os.environ.get('SMTP_TO','preview@example.invalid')
    # One delivery per trading day + mode + recipients, regardless of rerun/data revisions.
    key=hashlib.sha256((report['asof']+report['mode']+msg['To']).encode()).hexdigest()
    msg['Message-ID']=f'<{key}@equitybot.local>'
    msg.set_content('请使用支持HTML的客户端查看；本报告仅供研究观察，不是实际持仓或交易指令。')
    msg.add_alternative(html,subtype='html')
    (path/'email.eml').write_bytes(msg.as_bytes())
    if not send or os.environ.get('MAIL_SEND_ENABLED','false').lower()!='true': return 'preview'
    if report['mode']!='live': raise ValueError('演示数据禁止实际发信')
    required=['SMTP_HOST','SMTP_FROM','SMTP_TO']
    if any(not os.environ.get(k) for k in required): raise ValueError('SMTP配置不完整')
    db=store.db
    db.execute('BEGIN IMMEDIATE')
    row=db.execute('SELECT state,attempts FROM mail WHERE id=?',(key,)).fetchone()
    if row and row[0] in ('sent','sending','unknown'):
        db.rollback(); return 'duplicate-or-unknown'
    attempts=(row[1] if row else 0)+1
    if attempts>3: db.rollback(); return 'retry-exhausted'
    db.execute('INSERT OR REPLACE INTO mail(id,state,attempts) VALUES (?,?,?)',(key,'sending',attempts)); db.commit()
    started=False
    try:
        factory=smtp_factory or smtplib.SMTP
        with factory(os.environ['SMTP_HOST'],int(os.environ.get('SMTP_PORT','587')),timeout=20) as smtp:
            smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
            if os.environ.get('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.environ.get('SMTP_PASSWORD',''))
            started=True
            refused=smtp.send_message(msg)
            if refused: raise RuntimeError('partial recipient acceptance')
        state='sent'; error=None
    except Exception as e:
        # Before DATA handoff safe to retry; after handoff require manual reconciliation.
        state='unknown' if started else 'failed'; error=type(e).__name__
    db.execute('UPDATE mail SET state=?,error=?,updated=CURRENT_TIMESTAMP WHERE id=?',(state,error,key)); db.commit()
    return state
