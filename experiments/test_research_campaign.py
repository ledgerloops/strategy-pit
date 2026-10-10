import json
from pathlib import Path
import sys
import tempfile
import unittest
from research_campaign import run_campaign, load_manifest


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ledgerloops-campaign-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'fixture.txt'
        self.source.write_text('input')
        self.output = self.root/'output.json'
        self.state = self.root/'state.json'
        self.manifest = self.root/'manifest.json'

    def write(self, code=None, argv=None, timeout=3):
        code = code or 'import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("ok")'
        manifest = dict(version=1,jobs=[dict(id='test',argv=argv or [sys.executable,'-c',code,str(self.output)],
                        sources=[str(self.source)],inputs=[],outputs=[str(self.output)],timeout_seconds=timeout)])
        self.manifest.write_text(json.dumps(manifest))
        return manifest

    def read(self):
        return json.loads(self.state.read_text())

    def test_resume_verifies_sources_and_outputs(self):
        self.write()
        self.assertEqual(run_campaign(self.manifest,self.state),0)
        self.assertEqual(self.read()['jobs']['test']['attempts'],1)
        with self.assertRaises(ValueError):
            run_campaign(self.manifest,self.state)
        self.assertEqual(run_campaign(self.manifest,self.state,resume=True),0)
        self.assertEqual(self.read()['jobs']['test']['attempts'],1)
        self.output.write_text('corrupted')
        self.assertEqual(run_campaign(self.manifest,self.state,resume=True),0)
        self.assertEqual(self.read()['jobs']['test']['attempts'],2)
        self.source.write_text('changed')
        self.assertEqual(run_campaign(self.manifest,self.state,resume=True),0)
        self.assertEqual(self.read()['jobs']['test']['attempts'],3)

    def test_timeout_and_heartbeat(self):
        self.write(code='import time; time.sleep(3)',timeout=.1)
        self.assertEqual(run_campaign(self.manifest,self.state,heartbeat_seconds=.02),1)
        state = self.read()
        self.assertEqual(state['jobs']['test']['status'],'failed')
        self.assertIn('budget',state['jobs']['test']['error'])
        self.assertIn('heartbeat_at',state)

    def test_shell_metacharacters_literal(self):
        malicious = '$(touch '+str(self.root/'INJECTED')+')'
        self.write(argv=[sys.executable,'-c','import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])',str(self.output),malicious])
        self.assertEqual(run_campaign(self.manifest,self.state),0)
        self.assertEqual(self.output.read_text(),malicious)
        self.assertFalse((self.root/'INJECTED').exists())

    def test_missing_output_and_manifest_change(self):
        manifest = self.write(code='pass')
        self.assertEqual(run_campaign(self.manifest,self.state),1)
        manifest['jobs'][0]['timeout_seconds']=2
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            run_campaign(self.manifest,self.state,resume=True)

    def test_incomplete_benchmark_not_completed(self):
        manifest = self.write(code="import pathlib,sys,json; pathlib.Path(sys.argv[1]).write_text(json.dumps(dict(complete=False)))")
        manifest['jobs'][0]['require_json_complete'] = True
        self.manifest.write_text(json.dumps(manifest))
        self.assertEqual(run_campaign(self.manifest,self.state),1)
        self.assertIn('not marked complete',self.read()['jobs']['test']['error'])

    def test_no_output_outside_allowed_roots(self):
        manifest = self.write()
        manifest['jobs'][0]['outputs']=['/workspace/outside-results.json']
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            load_manifest(self.manifest)


if __name__ == '__main__':
    unittest.main()
