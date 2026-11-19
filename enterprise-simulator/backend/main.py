import asyncio,csv,io,json,os,random,sqlite3,time
from datetime import datetime,timezone
from contextlib import asynccontextmanager,contextmanager
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,Field
DB=os.getenv('DB_PATH','data/simulator.db')
PLATFORMS={'github':['Organization','Repository','Team','Branch','Commit','Pull request','Issue'],'aws':['IAM role','IAM group','IAM policy','Access key','EC2','S3','RDS','Lambda'],'windows':['Domain','OU','Security group','Workstation','Windows server'],'linux':['Linux server','User group','File','Service']}
ROLES={'Engineering':('Developer',['github','linux']),'IT Operations':('DevOps engineer',['aws','linux','windows']),'Finance':('Finance analyst',['windows']),'Human Resources':('HR specialist',['windows']),'Management':('Manager',['windows','github']),'Security':('System administrator',list(PLATFORMS))}
@contextmanager
def db():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
 try:
  yield c;c.commit()
 except: c.rollback();raise
 finally:c.close()
def init():
 os.makedirs(os.path.dirname(DB) or '.',exist_ok=True)
 with db() as c:
  c.executescript('''PRAGMA journal_mode=WAL;
  CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY,name TEXT,industry TEXT,locations TEXT,platforms TEXT,seed INTEGER,start_hour INTEGER,end_hour INTEGER,speed REAL,eps INTEGER,active_pct INTEGER,exception_pct INTEGER,state TEXT DEFAULT 'stopped',clock REAL,seq INTEGER DEFAULT 0);
  CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY,company INTEGER REFERENCES companies(id) ON DELETE CASCADE,name TEXT,email TEXT,department TEXT,title TEXT,manager INTEGER,status TEXT DEFAULT 'active',last_activity TEXT,UNIQUE(company,email));
  CREATE INDEX IF NOT EXISTS emp_company ON employees(company,id);
  CREATE TABLE IF NOT EXISTS resources(id INTEGER PRIMARY KEY,company INTEGER REFERENCES companies(id) ON DELETE CASCADE,platform TEXT,kind TEXT,name TEXT,state TEXT,metadata TEXT DEFAULT '{}',UNIQUE(company,platform,kind,name));
  CREATE INDEX IF NOT EXISTS res_company ON resources(company,platform,kind);
  CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY,company INTEGER REFERENCES companies(id) ON DELETE CASCADE,employee INTEGER REFERENCES employees(id) ON DELETE CASCADE,platform TEXT,status TEXT,permission TEXT,UNIQUE(employee,platform));
  CREATE INDEX IF NOT EXISTS acc_company ON accounts(company,platform,employee);
  CREATE TABLE IF NOT EXISTS grants(company INTEGER REFERENCES companies(id) ON DELETE CASCADE,employee INTEGER REFERENCES employees(id) ON DELETE CASCADE,resource INTEGER REFERENCES resources(id) ON DELETE CASCADE,permission TEXT,PRIMARY KEY(employee,resource));
  CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,company INTEGER REFERENCES companies(id) ON DELETE CASCADE,employee INTEGER,actor TEXT,platform TEXT,ts TEXT,ip TEXT,action TEXT,resource TEXT,result TEXT,raw TEXT);
  CREATE INDEX IF NOT EXISTS event_company ON events(company,id); CREATE INDEX IF NOT EXISTS event_platform ON events(company,platform,id);''')
def rows(c,q,p=()):return [dict(x) for x in c.execute(q,p)]
def one(c,q,p=()):
 r=c.execute(q,p).fetchone()
 if not r:raise HTTPException(404,'Not found')
 return dict(r)
def company(c,i):return one(c,'SELECT * FROM companies WHERE id=?',(i,))
def stamp(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
def event(c,co,p,action,resource,emp=None,result='success',ip='192.0.2.1',details=None):
 actor=emp['name'] if emp else 'Simulator administrator';ts=stamp(co['clock']);ei=emp['id'] if emp else None
 raw={'simulated':True,'companyId':co['id'],'employeeId':ei,'result':result}
 if p=='github':raw.update(action=action,actor=actor,repo=resource,created_at=int(co['clock']*1000),actor_ip=ip)
 elif p=='aws':raw.update(eventVersion='1.09',eventTime=ts,eventName=action,userIdentity={'type':'IAMUser','userName':actor},sourceIPAddress=ip,requestParameters={'resource':resource},**({'errorCode':'AccessDenied'} if result!='success' else {}))
 elif p=='windows':raw.update(EventID={'login':4624 if result=='success' else 4625,'logout':4634,'password.change':4723,'account.create':4720,'account.delete':4726,'group.add':4728,'group.remove':4729,'account.disable':4725,'account.enable':4722,'rdp.connect':4624}.get(action,0),TimeCreated=ts,TargetUserName=actor,IpAddress=ip,Computer=resource)
 elif p=='linux':raw.update(message=f'<{38 if result=="success" else 36}>1 {ts} {resource.replace(" ","-")} simulator - - - {action} user={actor} src={ip} result={result}')
 else:raw.update(action=action,actor=actor,resource=resource,timestamp=ts)
 if details:raw['details']=details
 c.execute('INSERT INTO events(company,employee,actor,platform,ts,ip,action,resource,result,raw) VALUES(?,?,?,?,?,?,?,?,?,?)',(co['id'],ei,actor,p,ts,ip,action,resource,result,json.dumps(raw)))
 if ei:c.execute('UPDATE employees SET last_activity=? WHERE id=?',(ts,ei))
class CompanyIn(BaseModel):
 name:str=Field(min_length=1,max_length=100);industry:str='Technology';count:int=Field(100,ge=1,le=100000);locations:str='Colombo';platforms:list[str]=list(PLATFORMS);seed:int=42;start_hour:int=Field(8,ge=0,le=23);end_hour:int=Field(18,ge=1,le=24);speed:float=Field(60,gt=0,le=86400);eps:int=Field(10,ge=1,le=1000);active_pct:int=Field(80,ge=1,le=100);exception_pct:int=Field(2,ge=0,le=100)
class EmployeeIn(BaseModel):
 name:str;email:str;department:str;title:str;manager:int|None=None
class ResourceIn(BaseModel):
 platform:str;kind:str;name:str;state:str='active';metadata:dict={}
class AccessIn(BaseModel):
 platform:str;permission:str='read';status:str='active'
class GrantIn(BaseModel):
 employee:int;resource:int;permission:str
class Operation(BaseModel):
 action:str;value:str='';incomplete:bool=False
class Settings(BaseModel):
 speed:float=Field(60,gt=0,le=86400);eps:int=Field(10,ge=1,le=1000);active_pct:int=Field(80,ge=1,le=100);exception_pct:int=Field(2,ge=0,le=100)
def tick():
 with db() as c:
  for co in rows(c,"SELECT * FROM companies WHERE state='running'"):
   co['clock']+=co['speed'];seq=co['seq']+1;r=random.Random(co['seed']+seq);cid=co['id'];hour=datetime.fromtimestamp(co['clock'],timezone.utc).hour
   if co['start_hour']<=hour<co['end_hour']:
    bounds=c.execute('SELECT min(id),max(id) FROM employees WHERE company=?',(cid,)).fetchone()
    if bounds[0] is not None:
     for _ in range(co['eps']):
      if r.randrange(100)>=co['active_pct']:continue
      eid=r.randint(*bounds);emp=c.execute("SELECT * FROM employees WHERE company=? AND id=? AND status='active'",(cid,eid)).fetchone()
      if not emp:continue
      acc=rows(c,"SELECT * FROM accounts WHERE employee=? AND status='active' ORDER BY platform",(eid,))
      if not acc:continue
      a=r.choice(acc);p=a['platform'];res=rows(c,"SELECT r.*,g.permission AS grant_permission FROM grants g JOIN resources r ON r.id=g.resource WHERE g.employee=? AND r.platform=? AND r.state NOT IN ('deleted','stopped') ORDER BY r.id",(eid,p))
      target=r.choice(res) if res else None;w=target and a['permission'] in ('write','admin') and target['grant_permission'] in ('write','admin')
      actions={'github':['repo.clone','repo.view']+(['git.push','pull_request.open','issue.create'] if w else []),'aws':['DescribeInstances','ListBuckets']+(['PutObject','InvokeFunction'] if w else []),'windows':['login','logout','rdp.connect'],'linux':['ssh.login','ssh.logout']+(['file.write'] if w else [])+(['sudo.command'] if w and a['permission']=='admin' and target['grant_permission']=='admin' else [])}[p]
      fail=r.randrange(100)<co['exception_pct'];action=r.choice(actions) if not fail else {'github':'simulated.login','aws':'ConsoleLogin','windows':'login','linux':'ssh.login'}[p]
      event(c,co,p,action,target['name'] if target else p+' account',dict(emp),'failure' if fail or not target else 'success',f'192.0.2.{r.randint(2,254)}')
   c.execute('UPDATE companies SET clock=?,seq=? WHERE id=?',(co['clock'],seq,cid))
async def loop():
 while True:
  await asyncio.sleep(1)
  try:await asyncio.to_thread(tick)
  except Exception:import logging;logging.exception('Simulation tick failed')
@asynccontextmanager
async def lifespan(app):
 init();task=asyncio.create_task(loop());yield;task.cancel()
app=FastAPI(title='Virtual Enterprise Simulator',lifespan=lifespan)
@app.get('/api/health')
def health():return {'status':'ok','simulated':True}
@app.get('/api/companies')
def companies():
 with db() as c:return rows(c,'SELECT * FROM companies ORDER BY id')
@app.post('/api/companies')
def create(x:CompanyIn):
 if not x.platforms or not set(x.platforms)<=set(PLATFORMS) or x.start_hour>=x.end_hour:raise HTTPException(400,'Invalid platforms or work hours')
 with db() as c:
  cid=c.execute('INSERT INTO companies(name,industry,locations,platforms,seed,start_hour,end_hour,speed,eps,active_pct,exception_pct,clock) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(x.name,x.industry,x.locations,json.dumps(sorted(set(x.platforms))),x.seed,x.start_hour,x.end_hour,x.speed,x.eps,x.active_pct,x.exception_pct,datetime(2026,1,5,x.start_hour,tzinfo=timezone.utc).timestamp())).lastrowid
  co=company(c,cid);r=random.Random(x.seed);resources={}
  for p in set(x.platforms):
   resources[p]=[]
   for kind in PLATFORMS[p]:
    for j in range(3 if kind in ('Repository','EC2','Linux server','Workstation','Windows server') else 1):
     rid=c.execute('INSERT INTO resources(company,platform,kind,name,state) VALUES(?,?,?,?,?)',(cid,p,kind,f'{kind.lower().replace(" ","-")}-{j+1}','active')).lastrowid;resources[p].append(rid)
  first=['Alex','Jordan','Nimal','Amaya','Taylor','Sam','Chen','Priya','Maya','Daniel','Asha','Noah'];last=['Silva','Perera','Patel','Lee','Smith','Khan','Fernando','Brown','Wong','Jayasinghe'];managers={}
  for i in range(x.count):
   dep=list(ROLES)[i%len(ROLES)] if i<6 else r.choice(list(ROLES));title,ps=ROLES[dep];name=f'{r.choice(first)} {r.choice(last)}';eid=c.execute('INSERT INTO employees(company,name,email,department,title,manager) VALUES(?,?,?,?,?,?)',(cid,name,f'employee{i+1}@company{cid}.example',dep,'Department manager' if dep not in managers else title,managers.get(dep))).lastrowid;managers.setdefault(dep,eid)
   for p in sorted(set(ps)&set(x.platforms)):
    perm='admin' if dep=='Security' else 'write' if dep in ('Engineering','IT Operations') else 'read';c.execute('INSERT INTO accounts(company,employee,platform,status,permission) VALUES(?,?,?,?,?)',(cid,eid,p,'active',perm));c.executemany('INSERT INTO grants VALUES(?,?,?,?)',[(cid,eid,rid,perm) for rid in resources[p][:3]])
  event(c,co,'enterprise','company.create',x.name,details={'employees':x.count});return co
@app.get('/api/companies/{cid}/summary')
def summary(cid:int):
 with db() as c:
  co=company(c,cid);out={k:c.execute(f'SELECT count(*) FROM {k} WHERE company=?',(cid,)).fetchone()[0] for k in ['employees','accounts','resources','events']};out['departments']=c.execute('SELECT count(DISTINCT department) FROM employees WHERE company=?',(cid,)).fetchone()[0];out['online']=c.execute("SELECT count(*) FROM employees WHERE company=? AND status='active' AND last_activity>=?",(cid,stamp(co['clock']-300))).fetchone()[0];out['by_platform']=rows(c,'SELECT platform,count(*) AS count FROM events WHERE company=? GROUP BY platform',(cid,));out['inventory']=rows(c,'SELECT kind,count(*) AS count FROM resources WHERE company=? GROUP BY kind',(cid,));out['company']=co;return out
@app.get('/api/companies/{cid}/departments')
def departments(cid:int):
 with db() as c:company(c,cid);return rows(c,'SELECT department,count(*) AS employees FROM employees WHERE company=? GROUP BY department',(cid,))
@app.get('/api/companies/{cid}/{table}')
def listing(cid:int,table:str,offset:int=0,limit:int=50,q:str='',platform:str='',after:int=0):
 allowed={'employees':['name','email','department','title'],'resources':['name','kind'],'accounts':['platform','status','permission'],'grants':['permission'],'events':['actor','action','resource','result']};
 if table not in allowed:raise HTTPException(404,'Unknown collection')
 with db() as c:
  company(c,cid);where='company=?';args=[cid]
  if q:where+=' AND ('+' OR '.join(f'{k} LIKE ?' for k in allowed[table])+')';args += [f'%{q}%']*len(allowed[table])
  if platform and table in ('resources','accounts','events'):where+=' AND platform=?';args.append(platform)
  if table=='events' and after:where+=' AND id>?';args.append(after)
  order='employee,resource' if table=='grants' else 'id DESC' if table=='events' and not after else 'id';limit=max(1,min(limit,1000));return {'items':rows(c,f'SELECT * FROM {table} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?',[*args,limit,max(0,offset)]),'total':c.execute(f'SELECT count(*) FROM {table} WHERE {where}',args).fetchone()[0]}
@app.get('/api/companies/{cid}/employees/{eid}')
def profile(cid:int,eid:int):
 with db() as c:return {'employee':one(c,'SELECT * FROM employees WHERE company=? AND id=?',(cid,eid)),'accounts':rows(c,'SELECT * FROM accounts WHERE company=? AND employee=?',(cid,eid)),'grants':rows(c,'SELECT g.*,r.name,r.platform FROM grants g JOIN resources r ON r.id=g.resource WHERE g.company=? AND g.employee=?',(cid,eid))}
@app.post('/api/companies/{cid}/employees')
def hire(cid:int,x:EmployeeIn):
 with db() as c:
  co=company(c,cid)
  if x.manager:one(c,'SELECT id FROM employees WHERE company=? AND id=?',(cid,x.manager))
  eid=c.execute('INSERT INTO employees(company,name,email,department,title,manager) VALUES(?,?,?,?,?,?)',(cid,x.name,x.email,x.department,x.title,x.manager)).lastrowid;event(c,co,'enterprise','employee.hire',x.email);return {'id':eid}
@app.put('/api/companies/{cid}/employees/{eid}')
def edit(cid:int,eid:int,x:EmployeeIn):
 with db() as c:
  co=company(c,cid);one(c,'SELECT * FROM employees WHERE company=? AND id=?',(cid,eid))
  if x.manager:one(c,'SELECT id FROM employees WHERE company=? AND id=?',(cid,x.manager))
  c.execute('UPDATE employees SET name=?,email=?,department=?,title=?,manager=? WHERE company=? AND id=?',(x.name,x.email,x.department,x.title,x.manager,cid,eid));event(c,co,'enterprise','employee.update',x.email);return {'ok':True}
@app.post('/api/companies/{cid}/employees/{eid}/operation')
def emp_operation(cid:int,eid:int,x:Operation):
 with db() as c:
  co=company(c,cid);emp=one(c,'SELECT * FROM employees WHERE company=? AND id=?',(cid,eid))
  if x.action not in ('terminate','activate'):raise HTTPException(400,'Invalid operation')
  c.execute('UPDATE employees SET status=? WHERE id=?',('terminated' if x.action=='terminate' else 'active',eid))
  if x.action=='terminate' and not x.incomplete:
   for a in rows(c,'SELECT * FROM accounts WHERE employee=?',(eid,)):event(c,co,a['platform'],'account.disable',emp['email'])
   c.execute("UPDATE accounts SET status='disabled' WHERE employee=?",(eid,));c.execute('DELETE FROM grants WHERE employee=?',(eid,))
  event(c,co,'enterprise','employee.'+x.action,emp['email'],details={'incomplete':x.incomplete});return {'ok':True}
@app.put('/api/companies/{cid}/employees/{eid}/access')
def access(cid:int,eid:int,x:AccessIn):
 with db() as c:
  co=company(c,cid);emp=one(c,'SELECT * FROM employees WHERE company=? AND id=?',(cid,eid))
  if x.platform not in json.loads(co['platforms']) or x.permission not in ('read','write','admin') or x.status not in ('active','disabled','removed'):raise HTTPException(400,'Invalid access')
  old=c.execute('SELECT * FROM accounts WHERE employee=? AND platform=?',(eid,x.platform)).fetchone()
  if x.status=='removed':c.execute('DELETE FROM accounts WHERE employee=? AND platform=?',(eid,x.platform));c.execute('DELETE FROM grants WHERE employee=? AND resource IN (SELECT id FROM resources WHERE platform=? AND company=?)',(eid,x.platform,cid));action='account.delete'
  else:c.execute('INSERT INTO accounts(company,employee,platform,status,permission) VALUES(?,?,?,?,?) ON CONFLICT(employee,platform) DO UPDATE SET status=excluded.status,permission=excluded.permission',(cid,eid,x.platform,x.status,x.permission));action='account.disable' if x.status=='disabled' else 'account.create' if not old else 'account.enable' if old['status']=='disabled' else 'permission.change'
  event(c,co,x.platform,action,emp['email'],details=x.model_dump());return {'ok':True}
@app.post('/api/companies/{cid}/resources')
def resource(cid:int,x:ResourceIn):
 with db() as c:
  co=company(c,cid)
  if x.platform not in json.loads(co['platforms']) or x.kind not in PLATFORMS[x.platform]:raise HTTPException(400,'Invalid resource kind')
  rid=c.execute('INSERT INTO resources(company,platform,kind,name,state,metadata) VALUES(?,?,?,?,?,?)',(cid,x.platform,x.kind,x.name,x.state,json.dumps(x.metadata))).lastrowid;event(c,co,x.platform,'resource.create',x.name);return {'id':rid}
@app.post('/api/companies/{cid}/resources/{rid}/operation')
def res_operation(cid:int,rid:int,x:Operation):
 with db() as c:
  co=company(c,cid);res=one(c,'SELECT * FROM resources WHERE company=? AND id=?',(cid,rid));p=res['platform']
  if x.action in ('start','stop','delete'):c.execute('UPDATE resources SET state=? WHERE id=?',({'start':'active','stop':'stopped','delete':'deleted'}[x.action],rid))
  elif x.action=='rename':c.execute('UPDATE resources SET name=? WHERE id=?',(x.value,rid))
  else:raise HTTPException(400,'Unsupported resource operation')
  event(c,co,p,{'start':'StartInstances','stop':'StopInstances'}.get(x.action,x.action) if p=='aws' and res['kind']=='EC2' else 'resource.'+x.action,res['name']);return {'ok':True}
@app.put('/api/companies/{cid}/grants')
def grant(cid:int,x:GrantIn):
 with db() as c:
  co=company(c,cid);emp=one(c,'SELECT * FROM employees WHERE company=? AND id=?',(cid,x.employee));res=one(c,'SELECT * FROM resources WHERE company=? AND id=?',(cid,x.resource));a=one(c,'SELECT * FROM accounts WHERE employee=? AND platform=?',(x.employee,res['platform']))
  if x.permission=='remove':c.execute('DELETE FROM grants WHERE employee=? AND resource=?',(x.employee,x.resource))
  elif x.permission in ('read','write','admin') and a['status']=='active':c.execute('INSERT INTO grants VALUES(?,?,?,?) ON CONFLICT(employee,resource) DO UPDATE SET permission=excluded.permission',(cid,x.employee,x.resource,x.permission))
  else:raise HTTPException(400,'Invalid grant or disabled account')
  event(c,co,res['platform'],'group.remove' if x.permission=='remove' else 'group.add',res['name'],details=x.model_dump());return {'ok':True}
@app.put('/api/companies/{cid}/settings')
def settings(cid:int,x:Settings):
 with db() as c:
  co=company(c,cid);c.execute('UPDATE companies SET speed=?,eps=?,active_pct=?,exception_pct=? WHERE id=?',(x.speed,x.eps,x.active_pct,x.exception_pct,cid));event(c,co,'enterprise','simulation.settings',co['name']);return {'ok':True}
@app.post('/api/companies/{cid}/simulation/{action}')
def control(cid:int,action:str):
 with db() as c:
  co=company(c,cid)
  if action=='reset':c.execute('DELETE FROM events WHERE company=?',(cid,));c.execute('UPDATE employees SET last_activity=NULL WHERE company=?',(cid,));c.execute("UPDATE companies SET state='stopped',seq=0,clock=? WHERE id=?",(datetime(2026,1,5,co['start_hour'],tzinfo=timezone.utc).timestamp(),cid))
  elif action in ('start','resume','pause','stop'):c.execute('UPDATE companies SET state=? WHERE id=?',({'start':'running','resume':'running','pause':'paused','stop':'stopped'}[action],cid))
  else:raise HTTPException(400,'Invalid control')
  return {'ok':True}
@app.get('/api/companies/{cid}/stream/events')
async def stream(cid:int,request:Request,after:int=0):
 with db() as c:company(c,cid)
 async def generate():
  nonlocal after
  while not await request.is_disconnected():
   with db() as c:items=rows(c,'SELECT * FROM events WHERE company=? AND id>? ORDER BY id LIMIT 500',(cid,after))
   for item in items:after=item['id'];yield f'id: {after}\ndata: {json.dumps(item)}\n\n'
   if not items:yield ': heartbeat\n\n';await asyncio.sleep(1)
 return StreamingResponse(generate(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no','Cache-Control':'no-cache'})
@app.get('/api/companies/{cid}/export/{fmt}')
def export(cid:int,fmt:str):
 if fmt not in ('csv','json'):raise HTTPException(400,'Invalid export format')
 with db() as c:company(c,cid)
 def generate():
  with db() as c:
   cursor=c.execute('SELECT * FROM events WHERE company=? ORDER BY id',(cid,));first=True
   if fmt=='json':yield '['
   else:
    buf=io.StringIO();csv.writer(buf).writerow([d[0] for d in cursor.description]);yield buf.getvalue()
   for row in cursor:
    if fmt=='json':yield ('' if first else ',')+json.dumps(dict(row));first=False
    else:
     buf=io.StringIO();csv.writer(buf).writerow(["'"+str(v) if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for v in row]);yield buf.getvalue()
   if fmt=='json':yield ']'
 return StreamingResponse(generate(),media_type='text/csv' if fmt=='csv' else 'application/json',headers={'Content-Disposition':f'attachment; filename="events.{fmt}"'})
@app.exception_handler(sqlite3.IntegrityError)
async def integrity(request,exc):
 from fastapi.responses import JSONResponse
 return JSONResponse(status_code=409,content={'detail':'Duplicate or invalid database relationship'})
