#!/usr/bin/env python3
"""Deploy a committed LedgerLoops alpha to Heroku without printing credentials.

Default mode is read-only --check. Resource creation requires --deploy plus a
full committed SHA. Credentials come only from environment secret bindings.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

ORIGIN = 'https://app.ledgerloops.com'
HOSTNAME = 'app.ledgerloops.com'
HEROKU = 'https://api.heroku.com'
CLOUDFLARE = 'https://api.cloudflare.com/client/v4'
REQUIRED_SOURCE = ('app', 'Procfile', 'requirements.txt', '.python-version', '.slugignore')


class DeploymentError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None  # Never forward an API Authorization header to another host.


class Api:
    def __init__(self, token, base=HEROKU, opener=None):
        if not token or not token.strip():
            raise DeploymentError('Deployment credential is not configured')
        self.token, self.base = token, base
        self.opener = opener or build_opener(NoRedirect())

    def request(self, method, path, body=None):
        if not path.startswith('/') or '://' in path:
            raise DeploymentError('API request must use a relative path')
        headers = {'Authorization': 'Bearer '+self.token, 'Content-Type': 'application/json'}
        if self.base == HEROKU:
            headers['Accept'] = 'application/vnd.heroku+json; version=3'
        payload = None if body is None else json.dumps(body).encode()
        request = Request(self.base+path, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read()
            result = json.loads(raw) if raw else {}
        except HTTPError as error:
            # Provider bodies and URLs can contain signed source links or config.
            raise DeploymentError('Provider request failed with HTTP '+str(error.code), error.code) from None
        except (URLError, OSError, ValueError):
            raise DeploymentError('Provider request failed; inspect account/network access privately') from None
        if self.base == CLOUDFLARE:
            if result.get('success') is not True:
                raise DeploymentError('Cloudflare rejected the DNS request')
            return result.get('result')
        return result


def emit(phase, **public):
    print(json.dumps(dict(phase=phase, **public), sort_keys=True), flush=True)


def archive_commit(repo, commit, output):
    """Archive only committed deployment inputs, never working-tree data/secrets."""
    if not re.fullmatch(r'[0-9a-f]{40}', commit or ''):
        raise DeploymentError('--commit must be a full lowercase 40-character committed SHA')
    repo, output = Path(repo).resolve(), Path(output).resolve()
    commands = [
        ['git', 'cat-file', '-e', commit+'^{commit}'],
        *[['git', 'cat-file', '-e', commit+':'+name] for name in REQUIRED_SOURCE],
        ['git', 'archive', '--format=tar.gz', '--output='+str(output), commit, *REQUIRED_SOURCE],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=repo, capture_output=True, check=False)
        if result.returncode:
            raise DeploymentError('Pinned commit is unavailable or lacks required deployment files')
    return 'SHA256:'+hashlib.sha256(output.read_bytes()).hexdigest()


def upload_source(url, archive, opener=None):
    if urlsplit(url).scheme != 'https':
        raise DeploymentError('Source upload must use HTTPS')
    # Source URLs are short-lived credentials. Never print them or attach Heroku auth.
    # Heroku signs an empty Content-Type. Supplying a media type changes the
    # S3 signature; omitting the header makes urllib supply its own default.
    request = Request(url, data=Path(archive).read_bytes(), method='PUT',
                      headers={'Content-Type': ''})
    try:
        with (opener or build_opener(NoRedirect())).open(request, timeout=120) as response:
            response.read()
    except (HTTPError, URLError, OSError):
        raise DeploymentError('Source upload failed; no signed URL has been logged') from None


def wait_for(fetch, accepted, failed=(), *, timeout=1200, clock=time.monotonic, sleep=time.sleep):
    deadline = clock()+timeout
    while True:
        value = fetch()
        if accepted(value):
            return value
        if value.get('status') in failed:
            raise DeploymentError('Build/release failed; inspect the private Heroku dashboard')
        if clock() >= deadline:
            raise DeploymentError('Timed out waiting for provider readiness; resources are retained')
        sleep(3)


def get_app(api, app):
    try:
        return api.request('GET', '/apps/'+app)
    except DeploymentError as error:
        if error.status == 404:
            return None
        raise


def domain(api, app):
    return next((item for item in api.request('GET', '/apps/'+app+'/domains')
                 if item.get('hostname') == HOSTNAME), None)


def configure_dns(cf, zone_id, target):
    if not re.fullmatch(r'[0-9a-f]{32}', zone_id or ''):
        raise DeploymentError('CLOUDFLARE_ZONE_ID must identify the ledgerloops.com zone')
    zone = cf.request('GET', '/zones/'+zone_id)
    if zone.get('name') != 'ledgerloops.com':
        raise DeploymentError('Cloudflare zone is not ledgerloops.com')
    if not isinstance(target, str) or not target.rstrip('.').endswith('.herokudns.com'):
        raise DeploymentError('Unexpected Heroku DNS target')
    path = '/zones/'+zone_id+'/dns_records'
    records = cf.request('GET', path+'?name='+quote(HOSTNAME, safe=''))
    if any(record.get('type') != 'CNAME' or record.get('name') != HOSTNAME for record in records) or len(records) > 1:
        raise DeploymentError('Conflicting app DNS records require an explicit DNS migration; none were deleted')
    body = dict(type='CNAME', name=HOSTNAME, content=target.rstrip('.'), ttl=1, proxied=False)
    if records:
        existing = records[0]
        if existing.get('content', '').rstrip('.') == body['content'] and existing.get('proxied') is False:
            return
        cf.request('PUT', path+'/'+existing['id'], body)
    else:
        cf.request('POST', path, body)


def healthy(url, opener=None):
    if urlsplit(url).scheme != 'https':
        return False
    try:
        with (opener or build_opener(NoRedirect())).open(url.rstrip('/')+'/healthz', timeout=20) as response:
            result = json.load(response)
        return result.get('status') == 'ok' and result.get('service') == 'ledgerloops-alpha'
    except (HTTPError, URLError, OSError, ValueError):
        return False


def check(api, app):
    api.request('GET', '/account')
    info = get_app(api, app)
    if info is None:
        return dict(app=app, exists=False, credential_valid=True, deployed=False)
    configuration = api.request('GET', '/apps/'+app+'/config-vars')
    custom = domain(api, app)
    return dict(app=app, exists=True, credential_valid=True,
                database_configured=bool(configuration.get('DATABASE_URL')),
                origin_matches=configuration.get('PUBLIC_ORIGIN') == ORIGIN,
                dns_target=custom.get('cname') if custom else None,
                acm_status=custom.get('acm_status') if custom else None,
                custom_domain_healthy=healthy(ORIGIN))


def deploy(api, app, commit, archive, checksum, *, region='eu', dns=None,
           uploader=upload_source, waiter=wait_for):
    """Authorized mutation path; never rotates credentials or deletes resources."""
    api.request('GET', '/account')
    info = get_app(api, app)
    if info is None:
        info = api.request('POST', '/apps', dict(name=app, region=region, stack='heroku-24'))
        emit('app-created', app=app)
    base = '/apps/'+app
    configuration = api.request('GET', base+'/config-vars')
    if configuration.get('PUBLIC_ORIGIN') not in (None, '', ORIGIN):
        raise DeploymentError('Existing PUBLIC_ORIGIN differs; refusing to invalidate enrolled passkeys')
    # PATCH updates only these public keys and retains all account/node secrets.
    api.request('PATCH', base+'/config-vars', dict(PUBLIC_ORIGIN=ORIGIN, PYTHONUNBUFFERED='1', PGSSLMODE='require'))
    api.request('PUT', base+'/buildpack-installations', dict(updates=[dict(buildpack='heroku/python')]))
    if not configuration.get('DATABASE_URL'):
        addons = api.request('GET', base+'/addons')
        postgres = [item for item in addons if item.get('addon_service', {}).get('name') == 'heroku-postgresql']
        if not postgres:
            api.request('POST', base+'/addons', dict(plan='heroku-postgresql:essential-0', attachment=dict(name='DATABASE')))
            emit('database-provisioning', app=app)
        waiter(lambda: api.request('GET', base+'/config-vars'), lambda value: bool(value.get('DATABASE_URL')), timeout=900)
    source = api.request('POST', '/sources')['source_blob']
    if urlsplit(source['get_url']).scheme != 'https':
        raise DeploymentError('Source download URL must use HTTPS')
    uploader(source['put_url'], archive)
    build = api.request('POST', base+'/builds', dict(source_blob=dict(url=source['get_url'], version=commit, checksum=checksum)))
    emit('building', app=app, commit=commit)
    build = waiter(lambda: api.request('GET', base+'/builds/'+build['id']),
                   lambda value: value.get('status') == 'successful', ('failed',), timeout=1800)
    release_id = (build.get('release') or {}).get('id')
    if not release_id:
        raise DeploymentError('Build has no release; refusing to report deployment success')
    release = waiter(lambda: api.request('GET', base+'/releases/'+release_id),
                     lambda value: value.get('status') == 'succeeded', ('failed',), timeout=900)
    formation = api.request('GET', base+'/formation')
    updates = [dict(type='web', quantity=1, dyno_size=dict(name='Basic'))]
    # Older releases used a second dyno. Disable it if it remains in formation.
    if any(item.get('type') == 'worker' for item in formation):
        updates.append(dict(type='worker', quantity=0))
    api.request('PATCH', base+'/formation', dict(updates=updates))
    custom = domain(api, app)
    if custom is None:
        custom = api.request('POST', base+'/domains', dict(hostname=HOSTNAME, sni_endpoint=None))
    api.request('POST', base+'/acm')
    if not custom.get('cname'):
        custom = waiter(lambda: domain(api, app) or {}, lambda value: bool(value.get('cname')), timeout=180)
    if dns:
        configure_dns(dns[0], dns[1], custom['cname'])
        api.request('PATCH', base+'/acm')
    emit('released', app=app, commit=commit, release=release.get('version'),
         domain=HOSTNAME, dns_type='CNAME', dns_target=custom['cname'],
         custom_domain_healthy=healthy(ORIGIN))
    return dict(app=app, commit=commit, release=release.get('version'), dns_target=custom['cname'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True, help='Exact target Heroku app name')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Read-only readiness check (default)')
    mode.add_argument('--deploy', action='store_true', help='Create/update paid alpha infrastructure and deploy')
    parser.add_argument('--commit', help='Full SHA containing all deployment files; required with --deploy')
    parser.add_argument('--region', choices=('eu', 'us'), default='eu')
    parser.add_argument('--configure-dns', action='store_true', help='Upsert only app.ledgerloops.com using Cloudflare secrets')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,28}[a-z0-9]', args.app):
        parser.error('Use an exact valid Heroku app name (3–30 lowercase characters)')
    if args.configure_dns and not args.deploy:
        parser.error('--configure-dns requires --deploy')
    try:
        api = Api(os.environ.get('HEROKU_API_KEY'))
        if not args.deploy:
            emit('check', **check(api, args.app))
            return 0
        dns = None
        if args.configure_dns:
            zone_id = os.environ.get('CLOUDFLARE_ZONE_ID')
            cf = Api(os.environ.get('CLOUDFLARE_API_TOKEN'), CLOUDFLARE)
            if not re.fullmatch(r'[0-9a-f]{32}', zone_id or ''):
                raise DeploymentError('CLOUDFLARE_ZONE_ID is missing or invalid')
            if cf.request('GET', '/zones/'+zone_id).get('name') != 'ledgerloops.com':
                raise DeploymentError('Cloudflare zone is not ledgerloops.com')
            dns = (cf, zone_id)
        with tempfile.TemporaryDirectory(prefix='ledgerloops-deploy-') as temporary:
            archive = Path(temporary)/'source.tar.gz'
            checksum = archive_commit(Path(__file__).resolve().parents[1], args.commit, archive)
            deploy(api, args.app, args.commit, archive, checksum, region=args.region, dns=dns)
        return 0
    except DeploymentError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        # Avoid accidentally leaking signed URLs/config from third-party errors.
        print('Deployment failed ('+type(error).__name__+'); no provider payload was logged', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
