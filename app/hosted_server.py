"""HTTPS/session gateway. Algorithms run only within their own local node."""
from collections import defaultdict, deque
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_from_directory
from psycopg import IntegrityError as PostgresIntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix

from hosted_auth import HostedAuth, AuthError, COOKIE_NAME
from hosted_runtime import HostedRuntime
from hosted_storage import PgStoreFactory


def create_app(*, stores=None, origin=None, development=False):
    origin = origin or os.environ.get('PUBLIC_ORIGIN','https://app.ledgerloops.com')
    parsed=urlsplit(origin)
    if parsed.scheme != 'https' and not development:
        raise ValueError('Hosted alpha requires HTTPS')
    stores=stores or PgStoreFactory(os.environ['DATABASE_URL'],max_connections=3)
    stores.create('accounts')
    auth=HostedAuth(stores.connection('accounts'),origin=origin,rp_id=parsed.hostname,development=development,
                    recovery_codes_enabled=os.environ.get('LEDGERLOOPS_RECOVERY_CODES_ENABLED') == '1')
    runtime=HostedRuntime(stores,origin)
    app=Flask(__name__,static_folder=None)
    app.config['MAX_CONTENT_LENGTH']=65536
    app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
    app.extensions.update(hosted_auth=auth,hosted_runtime=runtime,hosted_stores=stores)
    rates=defaultdict(deque)
    rate_lock=threading.Lock()
    static=Path(__file__).parent/'static'

    def payload():
        if not request.is_json:
            raise ValueError('Content-Type application/json required')
        value=request.get_json()
        if not isinstance(value,dict):
            raise ValueError('JSON object required')
        return value

    def account(write=False):
        token=request.cookies.get(COOKIE_NAME,'')
        if write:
            result=auth.authorize(token,request.headers.get('X-CSRF-Token'),request.headers.get('Origin'))
        else:
            result=auth.session(token)['account']
        runtime.provision(result)
        return result

    @app.before_request
    def guards():
        if request.path != '/healthz' and request.host != parsed.netloc:
            return jsonify(error='Use the canonical application domain'),421
        if not development and request.scheme != 'https':
            return jsonify(error='HTTPS required'),400
        if request.path.startswith('/auth/'):
            if request.headers.get('Origin') != origin:
                return jsonify(error='Origin not allowed'),403
            key=request.remote_addr
            now=time.monotonic()
            with rate_lock:
                if len(rates)>10000:
                    for old in list(rates):
                        if not rates[old] or rates[old][-1] < now-60:
                            del rates[old]
                queue=rates[key]
                while queue and queue[0]<now-60:
                    queue.popleft()
                if len(queue)>=30:
                    return jsonify(error='Too many authentication attempts; try again shortly'),429
                queue.append(now)

    @app.after_request
    def security_headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        # Existing comfort diagrams use generated inline style attributes.
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if not development:
            response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    @app.errorhandler(AuthError)
    def bad_auth(error):
        return jsonify(error=str(error)),401

    @app.errorhandler(PermissionError)
    def forbidden(error):
        return jsonify(error='Authentication required'),403

    @app.errorhandler(ValueError)
    @app.errorhandler(KeyError)
    @app.errorhandler(TypeError)
    @app.errorhandler(sqlite3.IntegrityError)
    @app.errorhandler(PostgresIntegrityError)
    def bad_input(error):
        return jsonify(error=str(error) if isinstance(error,ValueError) else 'Invalid request'),400

    @app.errorhandler(413)
    def too_big(error):
        return jsonify(error='Request exceeds 64 KiB'),413

    @app.get('/healthz')
    def health():
        try:
            # Touch only the auth store; this never inspects a credit graph.
            auth.db.execute('SELECT 1').fetchone()
        except Exception:
            return jsonify(status='unavailable'),503
        return jsonify(status='ok',mode='TEST',service='ledgerloops-alpha')

    @app.get('/')
    def index():
        html=(static/'index.html').read_text()
        html=html.replace('<body>','<body data-hosted="true">')
        html=html.replace('<script src="/app.js" defer>', '<script src="/hosted-config.js"></script><script src="/app.js" defer>')
        return app.response_class(html,mimetype='text/html')

    @app.get('/login')
    def login():
        return send_from_directory(static,'hosted.html')

    @app.get('/hosted-config.js')
    def config():
        return app.response_class('window.LEDGERLOOPS_HOSTED = true;',mimetype='application/javascript')

    @app.get('/<asset>')
    def assets(asset):
        if asset not in ('app.js','style.css','logo.jpg','hosted.js','hosted.css'):
            return jsonify(error='Not found'),404
        return send_from_directory(static,asset)

    @app.get('/api/session')
    def session():
        result=auth.session(request.cookies.get(COOKIE_NAME,''))
        runtime.provision(result['account'])
        return jsonify(dict(result,hosted=True))

    @app.post('/auth/<path:action>')
    def authenticate(action):
        if action in ('recover','recovery/replace') and not auth.recovery_codes_enabled:
            return jsonify(error='Recovery codes are disabled'),404
        body=payload()
        browser_origin=request.headers.get('Origin')
        token=request.cookies.get(COOKIE_NAME,'')
        csrf=request.headers.get('X-CSRF-Token')
        if action=='demo/start':
            result=auth.start_demo(body.get('display_name'),browser_origin,token)
        elif action=='register/begin':
            result=auth.begin_registration(body.get('display_name'),browser_origin)
        elif action=='register/finish':
            result=auth.finish_registration(body.get('challenge_id'),body.get('credential'),browser_origin)
        elif action=='login/begin':
            result=auth.begin_authentication(browser_origin)
        elif action=='login/finish':
            result=auth.finish_authentication(body.get('challenge_id'),body.get('credential'),browser_origin)
        elif action=='passkey/begin':
            result=auth.begin_add_passkey(token,csrf,browser_origin)
        elif action=='passkey/finish':
            result=auth.finish_add_passkey(body.get('challenge_id'),body.get('credential'),token,csrf,browser_origin)
        elif action=='recover':
            result=auth.recover(body.get('account_id'),body.get('recovery_code'),browser_origin)
        elif action=='recovery/replace':
            result=auth.replace_recovery_codes(token,csrf,browser_origin)
        elif action=='logout':
            auth.logout(token,csrf,browser_origin)
            response=jsonify(ok=True)
            response.delete_cookie(COOKIE_NAME,path='/',secure=True,httponly=True,samesite='Lax')
            return response
        else:
            return jsonify(error='Not found'),404
        session_token=result.pop('session_token',None)
        # Session provisioning is retried by /api/session if interrupted. Do not
        # lose freshly issued recovery codes to an unrelated provisioning failure.
        response=jsonify(result)
        if session_token:
            response.set_cookie(COOKIE_NAME,session_token,max_age=result['expires']-int(auth.now()),
                                secure=True,httponly=True,samesite='Lax',path='/')
        return response

    @app.get('/api/state')
    def state():
        return jsonify(runtime.state(account()['node_id']))

    @app.route('/api/contacts/invite',methods=['POST'])
    def invite():
        owner=account(True); body=payload()
        return jsonify(runtime.invite(owner['node_id'],peer_name=body.get('peer_name',''),
                                      max_trust=body.get('max_trust',10)))

    @app.post('/api/invitations/preview')
    def preview_invite():
        if request.headers.get('Origin') != origin:
            return jsonify(error='Origin not allowed'),403
        return jsonify(runtime.preview_invite(payload().get('invite_token')))

    @app.post('/api/contacts/accept')
    def accept_invite():
        owner=account(True); body=payload()
        return jsonify(runtime.accept_invite(owner['node_id'],body.get('invite_token'),
                                            max_trust=body.get('max_trust',10)))

    @app.post('/api/automation')
    def automation():
        owner=account(True)
        return jsonify(runtime.automation(owner['node_id'],payload().get('enabled')))

    @app.post('/api/contacts/<peer>/rename')
    def rename_peer(peer):
        owner=account(True); body=payload()
        if set(body) != {'name'}:
            raise ValueError('Provide a peer name')
        return jsonify(runtime.rename(owner['node_id'],peer,body['name']))

    @app.route('/api/contacts/<peer>/messages',methods=['GET','POST'])
    def peer_messages(peer):
        owner=account(request.method=='POST')
        if request.method=='GET':
            return jsonify(runtime.messages(owner['node_id'],peer))
        body=payload()
        if set(body) != {'id','text'}:
            raise ValueError('Provide a message id and text')
        return jsonify(runtime.send_message(owner['node_id'],peer,body['id'],body['text']))

    @app.get('/api/contacts/<peer>/history')
    def peer_history(peer):
        owner=account()
        value=request.args.get('offset','0')
        if not value.isascii() or not value.isdecimal() or len(value)>10:
            raise ValueError('History offset must be a nonnegative bounded integer')
        return jsonify(runtime.history(owner['node_id'],peer,int(value)))

    @app.route('/api/<path:action>',methods=['GET','POST'])
    def node_api(action):
        write=request.method=='POST'
        owner=account(write)
        data=payload() if write else None
        with runtime.node(owner['node_id']) as node:
            if not write:
                if action=='obligations':
                    return jsonify(node.obligations())
                if action=='receipts':
                    return jsonify(node.receipts())
                if action.startswith('receipts/'):
                    row=node.db.execute('SELECT data FROM receipts WHERE id=?',(action.split('/')[-1],)).fetchone()
                    return (jsonify(json.loads(row[0])),200) if row else (jsonify(error='Receipt not found'),404)
            elif action=='discover':
                if data.get('mode','cancellation') not in ('cancellation','headroom'):
                    raise ValueError('Choose cancellation or comfort-zone headroom clearing')
                return jsonify(node.discover(data.get('amount'),mode=data.get('mode','cancellation')))
            elif action=='obligations':
                return jsonify(node.propose_obligation(data))
            elif action.startswith('obligations/') and action.endswith('/approve'):
                return jsonify(node.approve_obligation(action.split('/')[-2],data.get('digest')))
            elif action.startswith('obligations/') and action.endswith('/decline'):
                return jsonify(node.decline_obligation(action.split('/')[-2],data.get('digest')))
            elif action.startswith('contacts/') and action.endswith('/preferences'):
                return jsonify(node.set_preferences(action.split('/')[-2],data))
            elif action.startswith('proposals/') and action.endswith('/approve'):
                return jsonify(node.approve(action.split('/')[-2],data.get('digest')))
            elif action.startswith('proposals/') and action.endswith('/decline'):
                return jsonify(node.decline(action.split('/')[-2],data.get('digest')))
            elif action=='pause':
                if type(data.get('paused')) is not bool:
                    raise ValueError('paused must be boolean')
                node.db.execute("UPDATE meta SET v=? WHERE k='paused'",('true' if data['paused'] else 'false',))
                return jsonify(paused=data['paused'])
        return jsonify(error='Not found'),404

    @app.post('/nodes/<node_id>/peer/message')
    def peer_message(node_id):
        return jsonify(runtime.receive(node_id,request.headers.get('X-Peer-ID',''),
                                       request.headers.get('Authorization',''),payload()))

    return app
