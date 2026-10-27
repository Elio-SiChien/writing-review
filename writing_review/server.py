"""Loopback-only companion service with durable reviews and retryable memory jobs."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import argparse, hashlib, json, os, re, secrets, sqlite3, threading, time, webbrowser
import urllib.request, urllib.error
from . import memory
from . import handoff

STATIC = Path(__file__).parent/'static'
MAX_BYTES = 5_000_000

def default_data():
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'WritingReview'

def normalize(data):
    if not isinstance(data, dict) or not isinstance(data.get('paragraphs'), list) or not data['paragraphs']:
        raise ValueError('A review needs paragraphs')
    paragraphs = []
    for p in data['paragraphs']:
        if not isinstance(p, dict): raise ValueError('Invalid paragraph')
        pid = str(p.get('id',''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',pid): raise ValueError('Invalid paragraph ID')
        original = p.get('original',p.get('text',''))
        current = p.get('current',original)
        if not isinstance(original,str) or not isinstance(current,str): raise ValueError('Invalid text')
        paragraphs.append(dict(p,id=pid,original=original,current=current))
    if len({p['id'] for p in paragraphs}) != len(paragraphs): raise ValueError('Duplicate paragraph ID')
    source = data.get('sourceSha256') or hashlib.sha256(json.dumps([[p['id'],p['original']] for p in paragraphs],ensure_ascii=False).encode()).hexdigest()
    if not re.fullmatch(r'[a-fA-F0-9]{64}',source): raise ValueError('Invalid source hash')
    rid = str(data.get('id') or 'd'+source[:24])
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',rid): raise ValueError('Invalid review ID')
    comments = data.get('comments',[])
    if not isinstance(comments,list): raise ValueError('Invalid comments')
    for c in comments:
        if not isinstance(c,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',str(c.get('id',''))):
            raise ValueError('Invalid comment ID')
        if c.get('paragraphId') not in {p['id'] for p in paragraphs} or not isinstance(c.get('text'),str):
            raise ValueError('Invalid comment target')
    if len({c['id'] for c in comments}) != len(comments): raise ValueError('Duplicate comment ID')
    comments = [{k:v for k,v in c.items() if not k.startswith('_')} for c in comments]
    return dict(data,id=rid,sourceSha256=source,paragraphs=paragraphs,comments=comments,
                roundId=str(data.get('roundId') or source[:24]),
                title=str(data.get('title','Untitled review')),schemaVersion=2)

class Store:
    def __init__(self, folder, vault=None, model=None, review_dir=None, auto_extract=False):
        self.folder=Path(folder).resolve()
        self.folder.mkdir(parents=True,exist_ok=True)
        self.vault=Path(vault).resolve() if vault else None
        self.model=model
        self.auto_extract=auto_extract
        self.review_dir=Path(review_dir).resolve() if review_dir else (self.vault/'写作复利/批注收件箱' if self.vault else self.folder/'reviews')
        self.export_status={}
        self.lock=threading.RLock()
        self.db=sqlite3.connect(self.folder/'reviews.sqlite3',check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,version INTEGER,body TEXT);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,due REAL,status TEXT,error TEXT,version INTEGER);
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS history(id TEXT,version INTEGER,body TEXT,PRIMARY KEY(id,version));''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS lineage(review_id TEXT PRIMARY KEY,manuscript_id TEXT,
                        round_number INTEGER,parent_id TEXT,approved_version INTEGER)''')
        for (rid,) in self.db.execute('SELECT id FROM reviews').fetchall():
            self.db.execute('INSERT OR IGNORE INTO lineage VALUES(?,?,?,?,?)',(rid,'m'+hashlib.sha256(rid.encode()).hexdigest()[:24],1,None,None))
        if self.auto_extract:
            self.db.execute("UPDATE jobs SET status='pending',due=? WHERE status='running'",(time.time(),))
        self.db.commit()

    def get(self,rid):
        with self.lock:
            row=self.db.execute('SELECT version,body FROM reviews WHERE id=?',(rid,)).fetchone()
            if not row: raise KeyError(rid)
            result=json.loads(row[1]); result['version']=row[0]
            job=self.db.execute('SELECT status,error,version FROM jobs WHERE id=?',(rid,)).fetchone()
            result['learning']=({'status':job[0],'error':job[1],'version':job[2]} if job else {'status':'idle'}) if self.auto_extract else {'status':'manual'}
            result['storage']=self.export_status.get(rid,{'status':'pending','directory':str(self.review_dir/rid)})
            result['lineage']=self.lineage(rid)
            return result

    def lineage(self,rid):
        row=self.db.execute('SELECT manuscript_id,round_number,parent_id,approved_version FROM lineage WHERE review_id=?',(rid,)).fetchone()
        if not row:return None
        child=self.db.execute('SELECT review_id FROM lineage WHERE parent_id=?',(rid,)).fetchone()
        return dict(manuscriptId=row[0],roundNumber=row[1],parentReviewId=row[2],approvedVersion=row[3],nextReviewId=child[0] if child else None,readOnly=bool(child))

    def list(self):
        with self.lock:
            return [{'id':rid,'version':v,'title':json.loads(b)['title'],'lineage':self.lineage(rid)} for rid,v,b in self.db.execute('SELECT id,version,body FROM reviews ORDER BY rowid DESC')]

    def save(self,data,expected):
        data=normalize(data)
        data.pop('version',None); data.pop('learning',None);data.pop('storage',None);data.pop('lineage',None)
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row=self.db.execute('SELECT version,body FROM reviews WHERE id=?',(data['id'],)).fetchone()
            if row:
                old=json.loads(row[1])
                if self.lineage(data['id'])['readOnly']:raise RuntimeError('This round is archived. Your changes remain in browser recovery; use the latest round.')
                data['project']=old.get('project') or 'auto-'+hashlib.sha256(data['id'].encode()).hexdigest()[:16]
                if old['sourceSha256']!=data['sourceSha256'] or [p['original'] for p in old['paragraphs']]!=[p['original'] for p in data['paragraphs']]:
                    raise ValueError('Source version mismatch; import as a separate document')
                if expected!=row[0]: raise RuntimeError('Version conflict; local changes retained. Reload before saving.')
                encoded=json.dumps(data,ensure_ascii=False,sort_keys=True)
                if encoded==row[1]:
                    return self.export(data['id'])
            elif expected not in (None,0): raise RuntimeError('Missing document version')
            else:
                data.setdefault('project','auto-'+hashlib.sha256(data['id'].encode()).hexdigest()[:16])
                encoded=json.dumps(data,ensure_ascii=False,sort_keys=True)
            version=(row[0] if row else 0)+1
            self.db.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?)',(data['id'],version,encoded))
            self.db.execute('INSERT INTO history VALUES(?,?,?)',(data['id'],version,encoded))
            self.db.execute('INSERT OR IGNORE INTO lineage VALUES(?,?,?,?,?)',(data['id'],'m'+hashlib.sha256(data['id'].encode()).hexdigest()[:24],1,None,None))
            if data['comments']:
                self.db.execute('INSERT OR REPLACE INTO jobs VALUES(?,?,?,?,?)',(data['id'],time.time()+15,'pending','',version))
            self.db.commit()
            return self.export(data['id'])

    def link_legacy_rounds(self,parent_id,child_id):
        """One-time explicit local migration; not a browser endpoint or inference."""
        with self.lock,self.db:
            parent=self.get(parent_id);child=self.get(child_id)
            if parent_id==child_id:raise ValueError('A round cannot be its own parent')
            if child['lineage']['parentReviewId']==parent_id:return
            if parent['lineage']['nextReviewId'] or child['lineage']['parentReviewId'] or child['lineage']['nextReviewId']:
                raise ValueError('Existing lineage cannot be replaced')
            self.db.execute('UPDATE lineage SET manuscript_id=?,round_number=?,parent_id=?,approved_version=? WHERE review_id=?',
                            (parent['lineage']['manuscriptId'],parent['lineage']['roundNumber']+1,parent_id,parent['version'],child_id))

    def create_round(self,request):
        """Called by an assistant only after explicit approval in the user's chat.

        The server verifies the source version, not the external chat's approval.
        """
        parent_id=request['parentReviewId'];expected=request['expectedVersion']
        note=request.get('approvalNote','').strip()
        if not note:raise ValueError('Record the explicit user approval before creating a round')
        incoming=normalize(request['review'])
        responses=request.get('responses',[])
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            parent=self.get(parent_id)
            if parent['version']!=expected:raise RuntimeError('Source version changed; update the proposal before applying it')
            child_id='r'+hashlib.sha256((parent_id+'|'+incoming['sourceSha256']).encode()).hexdigest()[:24]
            if parent['lineage']['nextReviewId']:
                old=self.get(parent['lineage']['nextReviewId'])
                approval=old.get('approval',{})
                if old['id']==child_id and approval.get('responses')==responses and approval.get('sourceVersion')==expected and old['paragraphs']==incoming['paragraphs']:
                    return self.export(old['id'])
                raise RuntimeError('A new round already exists; do not replace it')
            ids={c['id'] for c in parent['comments']}
            if not isinstance(responses,list) or len(responses)!=len(ids) or {r.get('commentId') for r in responses}!=ids:
                raise ValueError('Every source comment needs exactly one response')
            if any(r.get('status') not in ('addressed','carried') or not str(r.get('action','')).strip() for r in responses):
                raise ValueError('Responses need addressed/carried status and an action')
            if incoming['comments']:raise ValueError('New comments are entered in the new round; carry source comments via responses')
            carried={r['commentId'] for r in responses if r['status']=='carried'}
            incoming.update(id=child_id,project=parent.get('project') or 'auto-'+hashlib.sha256(parent_id.encode()).hexdigest()[:16],
                            scope=parent.get('scope','introduction'),roundId=child_id,
                            approval={'sourceReviewId':parent_id,'sourceVersion':expected,'note':note,'responses':responses})
            incoming['comments']=[dict(c,carriedFrom=parent_id) for c in parent['comments'] if c['id'] in carried]
            incoming=normalize(incoming)
            for key in ['version','learning','storage','lineage']:incoming.pop(key,None)
            encoded=json.dumps(incoming,ensure_ascii=False,sort_keys=True)
            self.db.execute('INSERT INTO reviews VALUES(?,?,?)',(child_id,1,encoded))
            self.db.execute('INSERT INTO history VALUES(?,?,?)',(child_id,1,encoded))
            self.db.execute('INSERT INTO lineage VALUES(?,?,?,?,?)',(child_id,parent['lineage']['manuscriptId'],parent['lineage']['roundNumber']+1,parent_id,expected))
        return self.export(child_id)

    def export(self,rid):
        with self.lock:
            review=self.get(rid)
            try:self.export_status[rid]=handoff.write_review(self.review_dir,review)
            except Exception as exc:self.export_status[rid]={'status':'retry','directory':str(self.review_dir/rid),'error':str(exc)}
            return self.get(rid)

    def export_all(self):
        return [self.export(item['id'])['storage'] for item in self.list()]

    def state(self):
        row=self.db.execute("SELECT value FROM state WHERE key='memory'").fetchone()
        return json.loads(row[0]) if row else {}

    def learn_once(self, force=False, extractor=None):
        if not self.auto_extract and not force:return False
        with self.lock:
            job=self.db.execute("SELECT id,version FROM jobs WHERE status IN ('pending','retry') AND due<=? ORDER BY due LIMIT 1",(time.time()+1e12 if force else time.time(),)).fetchone()
            if not job:return False
            rid,version=job
            review=self.get(rid)
            self.db.execute("UPDATE jobs SET status='running',error='' WHERE id=?",(rid,));self.db.commit()
        try:
            if not self.vault or not self.vault.is_dir(): raise RuntimeError('Obsidian vault is not configured or unavailable')
            context=memory.profile(self.vault,{'academic',str(review.get('scope','')),'project:'+str(review.get('project',''))})
            rules=extractor(review,context,self.folder/'worker') if extractor else memory.extract(review,context,self.folder/'worker',model=self.model)
            with self.lock:
                latest=self.get(rid)
                if latest['version']!=version:
                    # A newer save already queued another job. Do not apply stale suggestions.
                    return True
                allowed={c['id'] for c in review['comments']}
                for rule in rules:
                    if not memory.valid_scope(rule.get('scope','')) or not rule.get('source_ids') or not set(rule['source_ids'])<=allowed:
                        raise ValueError('Proposal has invalid scope or sources')
                # Even opt-in inference only prepares a proposal. The user's chat
                # approval is required before an assistant applies active preferences.
                proposal={'reviewId':rid,'sourceVersion':version,'status':'needs_user_approval','rules':rules}
                memory.atomic(self.folder/'proposals'/(rid+'-v'+str(version)+'.json'),json.dumps(proposal,ensure_ascii=False,indent=2))
                self.db.execute("UPDATE jobs SET status='proposal',error='' WHERE id=? AND version=?",(rid,version))
                self.db.commit()
        except Exception as exc:
            with self.lock:
                self.db.execute("UPDATE jobs SET status='retry',due=?,error=? WHERE id=? AND version=?",(time.time()+60,str(exc)[-800:],rid,version));self.db.commit()
        return True

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,code,data,kind='application/json; charset=utf-8'):
        raw=data.encode() if isinstance(data,str) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Writing-Review','1')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        try:self.end_headers();self.wfile.write(raw)
        except ConnectionError:pass  # A refresh may cancel a pending polling response.

    def allowed(self,api=False):
        origin='http://'+self.server.address
        if self.headers.get('Host')!=self.server.address:return False
        if self.headers.get('Origin') not in (None,origin):return False
        if self.headers.get('Sec-Fetch-Site')=='cross-site':return False
        return not api or secrets.compare_digest(self.headers.get('X-Review-Token',''),self.server.token)

    def do_GET(self):
        parsed=urlparse(self.path);path=parsed.path
        if not self.allowed(path.startswith('/api/')):return self.reply(403,{'error':'Local origin or token required'})
        try:
            if path=='/api/reviews':return self.reply(200,self.server.store.list())
            if path=='/api/storage':return self.reply(200,{'directory':str(self.server.store.review_dir),'autoExtract':self.server.store.auto_extract,'inVault':bool(self.server.store.vault and self.server.store.review_dir.is_relative_to(self.server.store.vault))})
            if path.startswith('/api/reviews/'):
                return self.reply(200,self.server.store.get(path.rsplit('/',1)[1]))
            if path=='/api/profile':
                scopes=parse_qs(parsed.query).get('scope',['academic','introduction'])
                vault=self.server.store.vault
                return self.reply(200,{'text':memory.profile(vault,scopes) if vault else '', 'configured':bool(vault)})
            if path=='/':
                text=(STATIC/'index.html').read_text(encoding='utf-8').replace('__TOKEN__',self.server.token)
                return self.reply(200,text,'text/html; charset=utf-8')
            if path in ('/app.js','/style.css'):
                return self.reply(200,(STATIC/path[1:]).read_text(encoding='utf-8'),'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
            self.reply(404,{'error':'Not found'})
        except KeyError:self.reply(404,{'error':'Review not found'})
        except Exception:self.reply(500,{'error':'Unable to read local data'})

    def do_POST(self):
        if not self.allowed(True):return self.reply(403,{'error':'Local origin or token required'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>MAX_BYTES:raise ValueError('Request too large or empty')
            if 'application/json' not in self.headers.get('Content-Type',''):raise ValueError('JSON required')
            data=json.loads(self.rfile.read(size))
            if self.path=='/api/save':return self.reply(200,self.server.store.save(data['review'],data.get('expectedVersion')))
            if self.path=='/api/rounds':return self.reply(200,self.server.store.create_round(data))
            if self.path=='/api/export':return self.reply(200,self.server.store.export(data['id']))
            if self.path=='/api/retry':
                if not self.server.store.auto_extract:raise ValueError('Automatic extraction is disabled; read the saved review files instead')
                with self.server.store.lock:
                    self.server.store.db.execute("UPDATE jobs SET due=?,status='pending' WHERE id=? AND status='retry'",(time.time(),data['id']))
                    self.server.store.db.commit()
                return self.reply(200,{'ok':True})
            self.reply(404,{'error':'Not found'})
        except (ValueError,KeyError,TypeError) as exc:self.reply(400,{'error':str(exc)})
        except RuntimeError as exc:self.reply(409,{'error':str(exc)})
        except Exception:self.reply(500,{'error':'Local save failed; export a backup'})

def make_server(store,port=8765):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.address='127.0.0.1:'+str(server.server_port)
    server.token=secrets.token_urlsafe(32)
    server.store=store
    return server

def main():
    parser=argparse.ArgumentParser(description='Local writing review. No external web server.')
    parser.add_argument('--data-dir',type=Path,default=default_data())
    parser.add_argument('--vault',type=Path)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--codex-model',help='Optional explicit model for extraction; otherwise inherit Codex configuration')
    parser.add_argument('--review-dir',type=Path,help='Fixed directory for JSON/Markdown handoff; defaults to vault writing inbox or private data/reviews')
    parser.add_argument('--auto-extract',action='store_true',help='Explicitly enable optional Codex background extraction; off by default')
    parser.add_argument('--profile',nargs='+',help='Print active scoped preferences and exit')
    args=parser.parse_args()
    config=args.data_dir/'config.json'
    saved=json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    vault=args.vault or saved.get('vault')
    if args.vault:saved['vault']=str(args.vault.resolve())
    if args.codex_model:saved['codex_model']=args.codex_model
    if args.review_dir:saved['review_dir']=str(args.review_dir.resolve())
    if args.vault or args.codex_model or args.review_dir:memory.atomic(config,json.dumps(saved,ensure_ascii=False))
    if args.profile:
        if not vault:parser.error('--vault is required the first time')
        print(memory.profile(vault,args.profile));return
    # Reopening the launcher must not reset a running job or spawn another worker.
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(args.port)+'/',timeout=1) as response:
            if response.headers.get('X-Writing-Review')=='1':
                if not args.no_browser:webbrowser.open('http://127.0.0.1:'+str(args.port))
                print('Writing Review is already running. Restart it to apply changed settings.')
                return
            parser.error('Port is already in use by another application')
    except urllib.error.URLError:
        pass
    store=Store(args.data_dir,vault,args.codex_model or saved.get('codex_model'),args.review_dir or saved.get('review_dir'),args.auto_extract)
    store.export_all()
    server=make_server(store,args.port)
    stop=threading.Event()
    def worker():
        while not stop.wait(2):
            if any(s.get('status')=='retry' for s in store.export_status.values()):store.export_all()
            if store.auto_extract:store.learn_once()
    thread=threading.Thread(target=worker,daemon=True);thread.start()
    url='http://'+server.address
    print('Writing Review '+url+'\nReview files stay in '+str(store.review_dir)+'\nAutomatic model extraction: '+str(store.auto_extract),flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();server.server_close()

if __name__=='__main__':main()
