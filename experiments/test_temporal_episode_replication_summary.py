import unittest
from pathlib import Path
from copy import deepcopy
from temporal_episode_replication_summary import certified_result


class CertificationTests(unittest.TestCase):
    def test_uncertified_or_undrained_rows_never_scored(self):
        output=Path('/tmp/result.json');manifest=Path('/tmp/manifest.json')
        report={'complete':True}
        row={'complete':True,'audit':{'valid':True},'pending_envelopes':0,
             'pending_reservations':0,'pending_transfers':0,'exposure':{'censored':False}}
        job={'status':'completed'}
        child={'status':'completed','jobs':{'case':{'status':'completed',
               'output_sha256':{str(output):'result'},'source_input_sha256':{str(manifest):'manifest'}}}}
        def check(a,b,c,d):return certified_result(a,b,c,d,'case',output,'result',manifest,'manifest')
        self.assertTrue(check(report,row,job,child))
        for field in ('pending_envelopes','pending_reservations','pending_transfers'):
            changed=deepcopy(row);changed[field]=1
            self.assertFalse(check(report,changed,job,child))
        self.assertFalse(check(report,row,{'status':'pending'},child))
        changed=deepcopy(child);changed['status']='failed'
        self.assertFalse(check(report,row,job,changed))
        for field,key in [('output_sha256',str(output)),('source_input_sha256',str(manifest))]:
            changed=deepcopy(child);changed['jobs']['case'][field][key]='changed'
            self.assertFalse(check(report,row,job,changed))
        self.assertFalse(check({'complete':False},row,job,child))
        changed=deepcopy(row);changed['audit']['valid']=False
        self.assertFalse(check(report,changed,job,child))


if __name__=='__main__':unittest.main()
