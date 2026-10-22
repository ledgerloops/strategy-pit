"""Deployment orchestration tests; no live account, DNS or resource mutations."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from deploy_heroku import (Api, DeploymentError, ORIGIN, HOSTNAME, REQUIRED_SOURCE,
                           archive_commit, check, configure_dns, deploy, upload_source)


class FakeHeroku:
    def __init__(self, *, exists=True, database=True, origin=ORIGIN, old_worker=True):
        self.exists = exists
        self.calls = []
        self.old_worker = old_worker
        self.config = {'PUBLIC_ORIGIN': origin, 'EXISTING_SECRET': 'retained'}
        if database:
            self.config['DATABASE_URL'] = 'private-url-never-logged'

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == '/account': return {'id': 'account'}
        if path == '/apps/test-alpha':
            if not self.exists: raise DeploymentError('Missing', 404)
            return {'id': 'app'}
        if path == '/apps' and method == 'POST':
            self.exists = True
            return {'id': 'app'}
        if path.endswith('/config-vars'):
            if body: self.config.update(body)
            return dict(self.config)
        if path.endswith('/addons'):
            if method == 'GET': return []
            self.config['DATABASE_URL'] = 'new-private-url'
            return {'id': 'postgres'}
        if path == '/sources':
            return {'source_blob': {'put_url': 'https://sources.example/put?private=secret',
                                    'get_url': 'https://sources.example/get?private=secret'}}
        if path.endswith('/builds'):
            return {'id': 'build'}
        if path.endswith('/builds/build'):
            return {'id': 'build', 'status': 'succeeded', 'release': {'id': 'release'}}
        if path.endswith('/releases/release'):
            return {'status': 'succeeded', 'version': 3}
        if path.endswith('/formation') and method == 'GET':
            return [{'type': 'web'}] + ([{'type': 'worker'}] if self.old_worker else [])
        if path.endswith('/domains'):
            return [{'hostname': HOSTNAME, 'cname': 'alpha.herokudns.com', 'acm_status': 'pending'}]
        return {}


def immediate(fetch, accepted, failed=(), **kwargs):
    value = fetch()
    if not accepted(value): raise AssertionError('Fake provider was not ready')
    return value


class DeployTests(unittest.TestCase):
    @patch('deploy_heroku.healthy', return_value=False)
    def test_check_is_read_only_and_excludes_secrets(self, _):
        api = FakeHeroku()
        result = check(api, 'test-alpha')
        self.assertTrue(result['origin_matches'])
        self.assertTrue(all(method == 'GET' for method, _, _ in api.calls))
        self.assertNotIn('retained', json.dumps(result))
        self.assertNotIn('private-url', json.dumps(result))

    @patch('deploy_heroku.healthy', return_value=False)
    def test_deploy_retains_secrets_pins_source_and_waits_for_release(self, _):
        api = FakeHeroku()
        uploaded = []
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            deploy(api, 'test-alpha', 'a'*40, Path('/unused'), 'SHA256:checksum',
                   uploader=lambda url, path: uploaded.append((url,path)), waiter=immediate)
        self.assertEqual(api.config['EXISTING_SECRET'], 'retained')
        self.assertEqual(api.config['PGSSLMODE'], 'require')
        build = next(body for method, path, body in api.calls if method == 'POST' and path.endswith('/builds'))
        self.assertEqual(build['source_blob']['version'], 'a'*40)
        release_index = next(i for i,c in enumerate(api.calls) if c[1].endswith('/releases/release'))
        formation_index = next(i for i,c in enumerate(api.calls) if c[0] == 'PATCH' and c[1].endswith('/formation'))
        self.assertLess(release_index, formation_index)
        self.assertEqual(api.calls[formation_index][2]['updates'], [
            {'type': 'web', 'quantity': 1, 'dyno_size': {'name': 'Basic'}},
            {'type': 'worker', 'quantity': 0},
        ])
        self.assertFalse(any(path.endswith('/addons') for _,path,_ in api.calls))
        self.assertNotIn('private=secret', output.getvalue())
        self.assertNotIn('private-url', output.getvalue())

    @patch('deploy_heroku.healthy', return_value=False)
    def test_create_app_and_database_only_when_missing(self, _):
        api = FakeHeroku(exists=False, database=False, old_worker=False)
        with contextlib.redirect_stdout(io.StringIO()):
            deploy(api, 'test-alpha', 'a'*40, Path('/unused'), 'SHA256:checksum',
                   uploader=lambda *args: None, waiter=immediate)
        self.assertEqual(sum(method == 'POST' and path == '/apps' for method,path,_ in api.calls), 1)
        addon = next(body for method,path,body in api.calls if method == 'POST' and path.endswith('/addons'))
        self.assertEqual(addon['plan'], 'heroku-postgresql:essential-0')
        formation = next(body for method,path,body in api.calls if method == 'PATCH' and path.endswith('/formation'))
        self.assertEqual(formation['updates'], [{'type': 'web', 'quantity': 1, 'dyno_size': {'name': 'Basic'}}])

    def test_existing_passkey_origin_is_not_rewritten(self):
        api = FakeHeroku(origin='https://another.example')
        with self.assertRaises(DeploymentError):
            deploy(api, 'test-alpha', 'a'*40, Path('/unused'), 'SHA256:checksum')
        self.assertTrue(all(method == 'GET' for method,_,_ in api.calls))

    def test_archive_uses_committed_allowlist_not_working_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for command in (['git','init','-q'], ['git','config','user.email','fixture@example.test'],
                            ['git','config','user.name','Fixture']):
                subprocess.run(command, cwd=repo, check=True, capture_output=True)
            (repo/'app').mkdir()
            (repo/'app'/'server.py').write_text('committed')
            for name in REQUIRED_SOURCE[1:]: (repo/name).write_text('fixture')
            (repo/'not-deployed.txt').write_text('excluded')
            subprocess.run(['git','add','.'], cwd=repo, check=True, capture_output=True)
            subprocess.run(['git','-c','commit.gpgsign=false','commit','-qm','fixture'], cwd=repo, check=True, capture_output=True)
            commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip()
            (repo/'app'/'server.py').write_text('uncommitted')
            archive = repo/'source.tar.gz'
            self.assertTrue(archive_commit(repo, commit, archive).startswith('SHA256:'))
            with tarfile.open(archive) as source:
                self.assertEqual(source.extractfile('app/server.py').read(), b'committed')
                self.assertNotIn('not-deployed.txt', source.getnames())
            with self.assertRaises(DeploymentError): archive_commit(repo, 'HEAD', archive)

    def test_provider_error_does_not_echo_private_payload(self):
        class Broken:
            def open(self, *args, **kwargs):
                raise HTTPError('https://private.example?token=secret', 401, 'secret', {}, None)
        with self.assertRaises(DeploymentError) as caught:
            Api('private-key', opener=Broken()).request('GET','/account')
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(caught.exception.status, 401)

    def test_source_upload_preserves_signed_content_type_without_api_auth(self):
        requests = []
        class SourceStorage:
            def open(self, request, **kwargs):
                requests.append(request)
                if request.get_header('Content-type') != '':
                    raise HTTPError(request.full_url, 403, 'SignatureDoesNotMatch', {}, None)
                return contextlib.closing(io.BytesIO())
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'source.tar.gz'
            archive.write_bytes(b'committed-source')
            upload_source('https://sources.example/put?private=secret', archive,
                          opener=SourceStorage())
        self.assertEqual(requests[0].get_method(), 'PUT')
        self.assertEqual(requests[0].data, b'committed-source')
        self.assertIsNone(requests[0].get_header('Authorization'))

    def test_dns_refuses_wrong_zone_and_conflicting_record(self):
        class Cloudflare:
            def __init__(self, zone='ledgerloops.com'):
                self.zone, self.calls = zone, []
            def request(self, method, path, body=None):
                self.calls.append((method,path))
                return [{'type':'A','name':HOSTNAME}] if '/dns_records' in path else {'name':self.zone}
        for zone in ('wrong.example','ledgerloops.com'):
            cf=Cloudflare(zone)
            with self.assertRaises(DeploymentError): configure_dns(cf, 'a'*32, 'alpha.herokudns.com')
            self.assertTrue(all(method=='GET' for method,_ in cf.calls))


if __name__ == '__main__':
    unittest.main()
