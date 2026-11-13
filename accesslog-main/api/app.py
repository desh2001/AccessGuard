import os, hmac, datetime, re, time
from collections import Counter
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import jwt

DATABASE_URL=os.environ['DATABASE_URL']
ADMIN_USERNAME=os.environ.get('ADMIN_USERNAME','admin')
ADMIN_PASSWORD=os.environ['ADMIN_PASSWORD']
JWT_SECRET=os.environ['JWT_SECRET']
if len(ADMIN_PASSWORD)<12 or len(JWT_SECRET)<32:
    raise RuntimeError('ADMIN_PASSWORD must be >=12 characters and JWT_SECRET >=32 characters')
engine=create_engine(DATABASE_URL,pool_pre_ping=True,pool_size=5,max_overflow=5)
app=FastAPI(title='Dialog Access Review API',docs_url=None,redoc_url=None)
auth=HTTPBearer()

SCHEMA='''
CREATE TABLE IF NOT EXISTS events (
 id BIGSERIAL PRIMARY KEY,
 occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 device_id TEXT NOT NULL DEFAULT 'unknown',
 user_id TEXT,
 event_type TEXT NOT NULL DEFAULT 'OTHER',
 action TEXT NOT NULL DEFAULT 'OBSERVED',
 source TEXT NOT NULL DEFAULT 'syslog',
 severity TEXT NOT NULL DEFAULT 'info',
 source_ip TEXT,
 raw_message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_received_at ON events(received_at DESC);
CREATE INDEX IF NOT EXISTS ix_events_device ON events(device_id);
CREATE INDEX IF NOT EXISTS ix_events_type ON events(event_type);
'''
@app.on_event('startup')
def startup():
    for _ in range(30):
        try:
            with engine.begin() as conn:
                for sql in SCHEMA.strip().split(';'):
                    if sql.strip(): conn.execute(text(sql))
            return
        except OperationalError:
            time.sleep(2)
    raise RuntimeError('Database unavailable')

class Credentials(BaseModel):
    username:str
    password:str

@app.post('/api/login')
def login(data:Credentials):
    if not (hmac.compare_digest(data.username,ADMIN_USERNAME) and hmac.compare_digest(data.password,ADMIN_PASSWORD)):
        raise HTTPException(401,'Invalid login')
    exp=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=8)
    return {'token':jwt.encode({'sub':ADMIN_USERNAME,'exp':exp},JWT_SECRET,algorithm='HS256'),'expires_in':28800}

def require_user(credentials:HTTPAuthorizationCredentials=Depends(auth)):
    try:
        payload=jwt.decode(credentials.credentials,JWT_SECRET,algorithms=['HS256'])
        if payload.get('sub')!=ADMIN_USERNAME: raise ValueError('unknown user')
        return payload['sub']
    except Exception:
        raise HTTPException(401,'Invalid or expired session')

@app.get('/api/health')
def health():
    return {'status':'ok'}

@app.get('/api/summary')
def summary(user=Depends(require_user)):
    with engine.connect() as conn:
        total=conn.execute(text('SELECT count(*) FROM events')).scalar()
        failed=conn.execute(text("SELECT count(*) FROM events WHERE event_type='LOGIN_FAILED' AND received_at > NOW()-interval '24 hours'")).scalar()
        active=conn.execute(text("SELECT count(DISTINCT device_id) FROM events WHERE received_at > NOW()-interval '15 minutes'")).scalar()
        devices=conn.execute(text('SELECT count(DISTINCT device_id) FROM events')).scalar()
        rows=conn.execute(text("SELECT to_char(date_trunc('hour',received_at),'YYYY-MM-DD HH24:00') AS hour, count(*) AS total FROM events WHERE received_at > NOW()-interval '24 hours' GROUP BY 1 ORDER BY 1")).mappings().all()
        types=conn.execute(text('SELECT event_type, count(*) AS total FROM events GROUP BY event_type ORDER BY total DESC LIMIT 8')).mappings().all()
        return {'total_events':total,'failed_logins_24h':failed,'active_devices_15m':active,'devices_seen':devices,'hourly':[dict(r) for r in rows],'types':[dict(r) for r in types]}

@app.get('/api/events')
def events(limit:int=Query(100,ge=1,le=500),device:str='',event_type:str='',user=Depends(require_user)):
    q='SELECT id,occurred_at,received_at,device_id,user_id,event_type,action,source,severity,source_ip,raw_message FROM events WHERE 1=1'
    params={'limit':limit}
    if device: q+=' AND device_id ILIKE :device';params['device']='%'+device+'%'
    if event_type: q+=' AND event_type=:type';params['type']=event_type
    q+=' ORDER BY received_at DESC LIMIT :limit'
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(q),params).mappings().all()]

@app.get('/api/devices')
def devices(user=Depends(require_user)):
    with engine.connect() as conn:
        rows=conn.execute(text('SELECT device_id, max(received_at) AS last_seen, count(*) AS event_count, max(source_ip) AS source_ip FROM events GROUP BY device_id ORDER BY last_seen DESC LIMIT 500')).mappings().all()
        now=datetime.datetime.now(datetime.timezone.utc)
        return [{**dict(r),'status':'active' if (now-r['last_seen']).total_seconds()<900 else 'inactive'} for r in rows]

@app.get('/api/users')
def users(user=Depends(require_user)):
    with engine.connect() as conn:
        rows=conn.execute(text('SELECT user_id, count(*) AS event_count, count(DISTINCT device_id) AS devices, max(received_at) AS last_seen FROM events WHERE user_id IS NOT NULL GROUP BY user_id ORDER BY last_seen DESC LIMIT 200')).mappings().all()
        return [dict(r) for r in rows]

@app.get('/api/alerts')
def alerts(user=Depends(require_user)):
    with engine.connect() as conn:
        rows=conn.execute(text("SELECT device_id,coalesce(user_id,'unknown') AS user_id,count(*) AS failures,max(received_at) AS last_seen FROM events WHERE event_type='LOGIN_FAILED' AND received_at > NOW()-interval '1 hour' GROUP BY device_id,coalesce(user_id,'unknown') HAVING count(*) >= 5 ORDER BY failures DESC LIMIT 100")).mappings().all()
        return [{**dict(r),'rule':'5+ failed logins in one hour','severity':'high'} for r in rows]
