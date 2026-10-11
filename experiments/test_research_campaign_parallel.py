import json
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import os
import unittest
from research_campaign_parallel import run_parallel


class ParallelTests(unittest.TestCase):
    def test_completed_jobs_resume_with_exact_outputs(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as folder:
            root=Path(folder);script=root/'write.py'
            script.write_text('import json,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps({"complete":True}))\n')
            jobs=[]
            for i in range(2):
                out=root/f'out{i}.json'
                jobs.append(dict(id=f'job{i}',argv=['python3',str(script),str(out)],timeout_seconds=3,
                    sources=[str(script)],inputs=[],outputs=[str(out)],require_json_complete=True))
            manifest=root/'manifest.json';manifest.write_text(json.dumps(dict(version=1,jobs=jobs)))
            state=root/'state.json'
            self.assertEqual(run_parallel(manifest,state,max_workers=2,max_seconds=10),0)
            self.assertTrue(json.loads(state.read_text())['complete'])
            self.assertEqual(run_parallel(manifest,state,resume=True,max_workers=2,max_seconds=10),0)
            with self.assertRaises(ValueError):run_parallel(manifest,state,max_seconds=10)

    def test_noncomplete_child_output_never_promoted(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as folder:
            root=Path(folder);script=root/'write.py';output=root/'out.json'
            script.write_text('import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(\'{"complete": false}\')\n')
            job=dict(id='partial',argv=['python3',str(script),str(output)],timeout_seconds=3,
                     sources=[str(script)],inputs=[],outputs=[str(output)],require_json_complete=True)
            manifest=root/'manifest.json';manifest.write_text(json.dumps(dict(version=1,jobs=[job])))
            state=root/'state.json'
            self.assertEqual(run_parallel(manifest,state,max_seconds=10),1)
            self.assertFalse(json.loads(state.read_text())['complete'])
            self.assertEqual(json.loads(state.read_text())['jobs']['partial']['status'],'failed')


    def test_sigterm_cleans_running_and_late_launched_children(self):
        for delayed in (False,True):
            with self.subTest(delayed=delayed), tempfile.TemporaryDirectory(dir='/tmp') as folder:
                root=Path(folder);script=root/'sleep.py';pidfile=root/'pid';entered=root/'entered'
                script.write_text('import os,signal,time,sys\nfrom pathlib import Path\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nPath(sys.argv[1]).write_text(str(os.getpid()))\ntime.sleep(60)\n')
                job=dict(id='sleep',argv=[sys.executable,str(script),str(pidfile)],timeout_seconds=5,
                    sources=[str(script)],inputs=[],outputs=[str(root/'out.json')],require_json_complete=True)
                manifest=root/'manifest.json';manifest.write_text(json.dumps(dict(version=1,jobs=[job])))
                state=root/'state.json';launcher=root/'launch.py'
                code=f'import sys,time\nfrom pathlib import Path\nsys.path.insert(0,{str(Path(__file__).parent.resolve())!r})\nimport research_campaign_parallel as p\n'
                if delayed:
                    code+=f'original=p.run_campaign\ndef delay(*a,**kw):\n Path({str(entered)!r}).write_text("entered")\n time.sleep(.4)\n return original(*a,**kw)\np.run_campaign=delay\n'
                code+='p.main()\n';launcher.write_text(code)
                process=subprocess.Popen([sys.executable,str(launcher),str(manifest),'--state',str(state),'--max-seconds','10'])
                try:
                    target=entered if delayed else pidfile
                    limit=time.monotonic()+3
                    while not target.exists() and time.monotonic()<limit:time.sleep(.01)
                    self.assertTrue(target.exists())
                    started=time.monotonic();process.terminate();self.assertEqual(process.wait(timeout=3),1)
                    self.assertLess(time.monotonic()-started,3)
                    self.assertEqual(json.loads(state.read_text())['status'],'paused')
                    child=json.loads((root/'state-sleep-state.json').read_text())['jobs']['sleep']['process_pid']
                    with self.assertRaises(ProcessLookupError):os.kill(child,0)
                finally:
                    if process.poll() is None:process.kill();process.wait()


if __name__=='__main__':unittest.main()
