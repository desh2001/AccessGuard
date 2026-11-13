import socketserver, re, os, logging, time, datetime
import psycopg
from psycopg import OperationalError
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
DB=os.environ['DATABASE_URL']; PORT=int(os.getenv('SYSLOG_PORT','5514'))
SYSLOG_RE=re.compile(r'^(?:<\d{1,3}>\d?\s*)?(?:(?:\d{4}-\d\d-\d\dT\S+|[A-Z][a-z]{2}\s+\d+\s+\d\d:\d\d:\d\d)\s+)?(?P<host>[\w.:-]+)\s+(?P<message>.*)$')
USER_RE=re.compile(r'(?:for (?:invalid user )?|user[= :]\s*|account[= :]\s*)([\w.@-]{1,128})',re.I)

def classify(message):
    m=message.lower()
    if any(x in m for x in ('failed password','authentication failure','login failed','logon failure','4625')): return 'LOGIN_FAILED','LOGIN_FAILED','warning'
    if any(x in m for x in ('accepted password','session opened','login success','logon success','4624')): return 'LOGIN','LOGIN_SUCCESS','info'
    if 'sudo' in m or 'privilege' in m or '4672' in m: return 'PRIVILEGE','PRIVILEGE_USED','warning'
    if 'session closed' in m or 'logged out' in m or '4634' in m: return 'LOGOUT','LOGOUT','info'
    return 'OTHER','OBSERVED','info'

class TCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        ip=self.client_address[0]
        logging.info('Connection from %s',ip)
        try:
            with psycopg.connect(DB,autocommit=True) as conn:
                for raw in self.rfile:
                    if len(raw)>65536: continue
                    s=raw.decode('utf-8',errors='replace').strip()[:8192]
                    if not s: continue
                    match=SYSLOG_RE.match(s)
                    host=(match.group('host') if match else ip)[:128]
                    msg=(match.group('message') if match else s)[:8192]
                    # Source IP is the observed VPN client, not a claimed hostname.
                    ev,action,severity=classify(msg)
                    found=USER_RE.search(msg)
                    user=found.group(1) if found else None
                    try:
                        conn.execute('INSERT INTO events(device_id,user_id,event_type,action,source,severity,source_ip,raw_message) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',(host,user,ev,action,'syslog',severity,ip,s))
                    except Exception:
                        logging.exception('Unable to insert event')
        except Exception:
            logging.exception('Connection failed %s',ip)

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True

if __name__=='__main__':
    with Server(('0.0.0.0',PORT),TCPHandler) as server:
        logging.info('Collector listening on TCP %d',PORT)
        server.serve_forever()
