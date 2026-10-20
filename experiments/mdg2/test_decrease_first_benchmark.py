"""Follow-up fixture/schema/gate checks only; never runs performance workloads."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import decrease_first_benchmark as follow
import make_decrease_first_workloads as generator


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads(follow.PLAN.read_text())

    def examples(self,candidate=106,baseline=100):
        runs=[]
        for profile in ('broad','narrow'):
            for mode in ('static','arrivals'):
                for seed in (401,402,403):
                    for method,value in [('comfort_headroom',baseline),('decrease_first',candidate)]:
                        runs.append(dict(phase='heldout',budget_per_trustline=1024,profile=profile,mode=mode,
                            method=method,seed=seed,snapshot_savings=value,final=dict(messages=100,message_bytes=1000),
                            runtime_seconds=1,independent_audit_passed=True,accepted=20,offered=20,blocked=0,
                            pending_messages=0,pending_reservations=0))
        return runs

    def test_generator_reproduces_original_and_separates_fresh_seeds(self):
        generated=generator.build()
        original=json.loads(generator.ORIGINAL.read_text())
        self.assertEqual(generated['extension_cases'],original['cases'])
        self.assertEqual(len(generated['heldout_cases']),6)
        self.assertEqual({c['seed'] for c in generated['heldout_cases']},{401,402,403})
        for case in generated['heldout_cases']:
            self.assertEqual((len(case['nodes']),len(case['edges'])),(32,96))
        self.assertEqual(generated,json.loads(follow.WORKLOAD.read_text()))

    def test_exact_matrix_has_120_extension_and_48_heldout(self):
        inputs=generator.build()
        for phase,expected in [('extension',120),('heldout',48)]:
            spec=self.plan[phase]
            count=len(inputs[phase+'_cases'])*len(spec['modes'])*len(spec['methods'])*len(spec['budgets_per_original_trustline'])
            self.assertEqual(count,expected)

    def test_constructor_injection_restores_original_even_on_failure(self):
        original=follow.base.Network
        def mock_case(*args):
            self.assertIs(follow.base.Network,follow.DecreaseFirstNetwork)
            self.assertEqual(args[2],'comfort_headroom')
            return {'policy':'comfort_headroom'}
        with patch.object(follow.base,'run_case',side_effect=mock_case):
            self.assertEqual(follow.run_selected({},'static','decrease_first',1024,{}),{'policy':'comfort_headroom'})
        self.assertIs(follow.base.Network,original)
        with patch.object(follow.base,'run_case',side_effect=ValueError('test')):
            with self.assertRaises(ValueError):follow.run_selected({},'static','decrease_first',1024,{})
        self.assertIs(follow.base.Network,original)

    def test_gate_requires_pooled_gain_and_ignores_lower_budget_for_gain(self):
        runs=self.examples();self.assertTrue(follow.gate(runs,self.plan)['passed'])
        low=copy.deepcopy(runs)
        for run in low:run['budget_per_trustline']=256;run['snapshot_savings']=1000000 if run['method']=='decrease_first' else 1
        failing=self.examples(candidate=104)
        self.assertFalse(follow.gate(failing+low,self.plan)['passed'])

    def test_negative_and_zero_cell_edges_do_not_disappear(self):
        runs=self.examples(candidate=120,baseline=100)
        for run in runs:
            if (run['profile'],run['mode'])==('narrow','arrivals'):
                run['snapshot_savings']=-20 if run['method']=='comfort_headroom' else -21
        result=follow.gate(runs,self.plan)
        cell=next(c for c in result['cells'] if (c['profile'],c['mode'])==('narrow','arrivals'))
        self.assertTrue(cell['passed'])
        for run in runs:
            if (run['profile'],run['mode'])==('narrow','arrivals') and run['method']=='decrease_first':run['snapshot_savings']=-22
        self.assertFalse(follow.gate(runs,self.plan)['passed'])
        zero=self.examples(candidate=0,baseline=0)
        result=follow.gate(zero,self.plan)
        self.assertIsNone(result['pooled_gain_fraction']);self.assertFalse(result['passed'])
        self.assertTrue(all(c['passed'] and c['relative_change'] is None for c in result['cells']))

    def test_cost_zero_and_ceiling_edges(self):
        self.assertEqual(follow.fractional_metric(0,0,1.25),dict(candidate=0,control=0,ratio=None,passed=True))
        self.assertFalse(follow.fractional_metric(1,0,1.25)['passed'])
        self.assertTrue(follow.fractional_metric(125,100,1.25)['passed'])
        self.assertFalse(follow.fractional_metric(126,100,1.25)['passed'])
        runs=self.examples()
        for run in runs:
            if run['method']=='decrease_first':run['runtime_seconds']=1.26
        self.assertFalse(follow.gate(runs,self.plan)['passed'])

    def test_any_blocked_or_unaudited_run_prevents_promotion(self):
        runs=self.examples();runs[0]['blocked']=1
        self.assertFalse(follow.gate(runs,self.plan)['passed'])
        runs=self.examples();runs[0]['independent_audit_passed']=False
        self.assertFalse(follow.gate(runs,self.plan)['passed'])


if __name__=='__main__':unittest.main()
