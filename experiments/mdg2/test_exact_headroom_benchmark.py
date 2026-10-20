"""Runner/schema/freeze checks only; never executes the performance campaign."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_exact_headroom_workloads as generator

# The actor and auditor are independently developed. Importing the harness with
# placeholders keeps these tests independent and cannot accidentally launch it.
spec = importlib.util.spec_from_file_location('exact_runner_under_test', HERE/'exact_headroom_benchmark.py')
runner = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {
        'exact_headroom': types.SimpleNamespace(ExactNetwork=object),
        'exact_headroom_audit': types.SimpleNamespace(audit_run=lambda *args: None)}):
    spec.loader.exec_module(runner)


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now
    def advance(self, amount): self.now += amount


class HarnessNetwork:
    instances = []
    clock = None
    gross = 7
    exact_cost = 3
    control_cost = 3

    def __init__(self, edges, seed=0):
        self.clock.advance(2)
        self.messages = self.delivered = 0
        self.queue, self.receipts, self.calls, self.transfers = [], [], [], []
        self.actors = {a:types.SimpleNamespace(reservations={}) for edge in edges for a in edge[:2]}
        self.ledger = {(a,b):value for a,b,value,*_ in edges}
        type(self).instances.append(self)

    def transfer(self, a, b, amount):
        self.clock.advance(2)
        self.ledger[a,b] += amount
        self.transfers.append((a,b,amount))
        return True

    def clear_exact(self, policy, message_limit):
        self.clock.advance(2)
        self.calls.append(('exact',policy,message_limit))
        used = min(message_limit,self.exact_cost)
        self.messages += used; self.delivered += used
        if used == self.exact_cost: self.receipts.append(dict(id=len(self.calls)))
        return dict(status='certified' if used == self.exact_cost else 'incomplete',
                    certified=used == self.exact_cost,used_messages=used)

    def clear(self, policy, budget, max_hops):
        self.clock.advance(2)
        self.calls.append(('control',policy,budget,max_hops))
        used = min(budget,self.control_cost)
        self.messages += used; self.delivered += used
        return dict(used_messages=used)

    def score(self):
        self.clock.advance(1000)  # Scoring is deliberately expensive but excluded.
        return dict(gross_debt=self.gross,messages=self.messages,delivered_messages=self.delivered)

    def snapshot(self):
        self.clock.advance(1000)
        return [dict(source=a,target=b,balance=value) for (a,b),value in sorted(self.ledger.items())]


def mini_case(count=12):
    terms = dict(credit_limit=10000,comfort_min=-10000,comfort_max=10000,auto_adjust=True)
    edges = [dict(a=0,b=1,balance=1,own=dict(terms),peer=dict(terms)),
             dict(a=1,b=2,balance=-1,own=dict(terms),peer=dict(terms)),
             dict(a=0,b=2,balance=1,own=dict(terms),peer=dict(terms))]
    return dict(name='unit-broad',profile='broad',seed=501,nodes=[0,1,2],edges=edges,
                arrivals=[dict(time=i+1,a=0,b=1,amount=(-1 if i%2 else 1))for i in range(count)],sha256='fixture')


class ExactHarnessTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(runner.PLAN.read_text())
        self.small_plan = copy.deepcopy(self.plan)
        self.small_plan['arrivals']['epoch_size'] = 4
        self.small_plan['exact_total_message_safety_ceiling'] = 5
        self.small_plan['control_total_messages_per_trustline'] = 3
        HarnessNetwork.instances=[]
        HarnessNetwork.clock=Clock()
        self.oracle_calls=[]

    def fake_oracle(self, case, mode):
        HarnessNetwork.clock.advance(10000)
        self.oracle_calls.append((len(case['arrivals']),mode))
        return dict(reference_gross=5,minimum_gross=0,potential=5)

    def run_fake(self, case=None, method='exact',mode='arrivals',oracle=None):
        with patch.object(runner,'ExactNetwork',HarnessNetwork), \
             patch.object(runner,'DecreaseFirstNetwork',HarnessNetwork), \
             patch.object(runner,'oracle',side_effect=oracle or self.fake_oracle), \
             patch.object(runner.time,'perf_counter',HarnessNetwork.clock):
            return runner.run_case(case or mini_case(),method,mode,self.small_plan)

    def test_exact_ceiling_is_cumulative_across_epochs_and_exhaustion_is_retained(self):
        result=self.run_fake()
        net=HarnessNetwork.instances[-1]
        self.assertEqual([call[2]for call in net.calls],[5,2,0,0])
        self.assertEqual(result['final']['messages'],5)
        self.assertEqual(result['offered'],12)
        self.assertEqual(result['accepted'],12)
        self.assertEqual(result['blocked'],0)
        self.assertEqual([e['clear_result']['status']for e in result['epochs']],
                         ['certified','incomplete','incomplete','incomplete'])
        self.assertFalse(result['epochs'][-1]['clear_result']['certified'])
        self.assertEqual(sum(e['used_messages']for e in result['epochs']),5)
        self.assertEqual(len([e for e in result['audit_events']if e['kind']=='transfer']),12)
        self.assertEqual(result['pending_messages'],0)
        self.assertEqual(result['pending_reservations'],0)

    def test_control_credit_is_earned_once_and_unused_credit_carries(self):
        result=self.run_fake(method='decrease_first')
        epochs=result['epochs']
        self.assertEqual([e['earned_allowance']for e in epochs],[2,4,6,9])
        self.assertEqual([e['used_messages']for e in epochs],[2,2,2,3])
        self.assertEqual(result['final']['messages'],9)
        self.assertEqual(result['actual_messages_per_trustline'],3)
        self.assertEqual([e['prefix_count']for e in epochs],[0,4,8,12])
        self.assertEqual(self.oracle_calls,[(0,'static'),(4,'arrivals'),(8,'arrivals'),(12,'arrivals')])

    def test_every_transfer_is_before_its_epoch_settlement_and_no_future_oracle_prefix(self):
        result=self.run_fake()
        for epoch in result['epochs']:
            prefix=result['audit_events'][:epoch['event_end_index']]
            self.assertEqual(sum(event['kind']=='transfer'for event in prefix),epoch['prefix_count'])
        self.assertEqual(HarnessNetwork.instances[-1].transfers,
                         [(e['a'],e['b'],e['amount'])for e in mini_case()['arrivals']])

    def test_runtime_excludes_oracle_scoring_and_snapshot_work(self):
        result=self.run_fake()
        # Constructor +12 transfers +4 service calls each deliberately cost2.
        self.assertEqual(result['runtime_seconds'],2*(1+12+4))
        self.assertGreater(HarnessNetwork.clock.now,40000)
        self.assertEqual(len(self.oracle_calls),4)

    def test_negative_savings_remain_negative_and_zero_potential_is_undefined(self):
        negative=self.run_fake()
        self.assertTrue(all(e['snapshot_savings']==-2 for e in negative['epochs']))
        self.assertTrue(all(e['clearing_potential_achieved_percent']==-40 for e in negative['epochs']))
        HarnessNetwork.instances=[];HarnessNetwork.clock=Clock()
        undefined=self.run_fake(oracle=lambda *_:dict(reference_gross=5,minimum_gross=5,potential=0))
        self.assertTrue(all(e['clearing_potential_achieved_percent']is None for e in undefined['epochs']))

    def test_static_has_initial_service_and_no_arrivals(self):
        result=self.run_fake(mode='static')
        self.assertEqual(result['offered'],0)
        self.assertEqual(result['accepted'],0)
        self.assertEqual(result['touched_trustlines'],0)
        self.assertEqual(len(result['epochs']),1)
        self.assertEqual(HarnessNetwork.instances[-1].transfers,[])
        self.assertEqual(self.oracle_calls,[(0,'static')])

    def test_heavy_generator_is_deterministic_and_has_room_for_every_arrival(self):
        first=generator.build();second=generator.build()
        self.assertEqual(first,second)
        self.assertEqual(len(first['cases']),6)
        by_seed={}
        for case in first['cases']:
            self.assertEqual(len(case['nodes']),32)
            self.assertEqual(len(case['edges']),96)
            self.assertEqual(len(case['arrivals']),1000)
            pairs={(e['a'],e['b'])for e in case['edges']}
            self.assertEqual(len(pairs),96)
            self.assertTrue(all(a<b for a,b in pairs))
            self.assertEqual({(e['a'],e['b'])for e in case['arrivals']},pairs)
            self.assertTrue(all(a['time']<b['time']for a,b in zip(case['arrivals'],case['arrivals'][1:])))
            gross=sum(abs(e['balance'])for e in case['edges'])
            total_arrival_value=sum(abs(e['amount'])for e in case['arrivals'])
            self.assertLess(gross+total_arrival_value,10000)
            for edge in case['edges']:
                self.assertEqual(edge['own']['credit_limit'],10000)
                self.assertEqual(edge['peer']['credit_limit'],10000)
            saved=case['sha256'];without={k:v for k,v in case.items()if k!='sha256'}
            actual=hashlib.sha256(json.dumps(without,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            self.assertEqual(saved,actual)
            by_seed.setdefault(case['seed'],[]).append(case)
        self.assertEqual(set(by_seed),{501,502,503})
        for pair in by_seed.values():
            self.assertEqual(pair[0]['arrivals'],pair[1]['arrivals'])
            self.assertEqual([(e['a'],e['b'],e['balance'])for e in pair[0]['edges']],
                             [(e['a'],e['b'],e['balance'])for e in pair[1]['edges']])

    def test_plan_explicitly_distinguishes_costs_and_exactness_claims(self):
        self.assertEqual(self.plan['expected_runs'],15)
        self.assertEqual(self.plan['control_total_messages_per_trustline'],1024)
        self.assertGreater(self.plan['exact_total_message_safety_ceiling'],1024*96)
        self.assertIn('finite-budget',self.plan['control'])
        self.assertIn('not automatically',str(self.plan['primary_checks']))
        self.assertIn('no real-time throughput claim',self.plan['arrivals']['interpretation'])
        cases=generator.build()['cases'];matrix=[]
        for case in cases:
            for mode in self.plan['exact_modes'][case['profile']]:
                matrix.append((case['profile'],case['seed'],mode,'exact'))
                if mode in self.plan['control_modes'].get(case['profile'],[]):
                    matrix.append((case['profile'],case['seed'],mode,'decrease_first'))
        self.assertEqual(len(matrix),15)
        self.assertEqual(len(set(matrix)),15)
        self.assertEqual(sum(row[0]=='narrow'for row in matrix),3)
        self.assertFalse(any(row[0]=='narrow'and row[-1]=='decrease_first'for row in matrix))

    def test_prospective_manifest_covers_all_economic_code_and_detects_changes(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);here=root/'experiments'/'mdg2';here.mkdir(parents=True)
            (root/'app').mkdir();(root/'app'/'comfort.py').write_text('economic bounds')
            sources=['exact_headroom.py','exact_headroom_benchmark.py','exact_headroom_audit.py',
                     'make_exact_headroom_workloads.py','comfort_headroom.py','comfort_decrease_first.py',
                     'comfort_curve_benchmark.py','comfort_curve_audit.py']
            for name in sources:(here/name).write_text('source '+name)
            plan=here/'plan.json';plan.write_text('{}')
            workload=here/'workload.json';workload.write_text('{}')
            with patch.multiple(runner,HERE=here,ROOT=root,PLAN=plan,INPUT=workload):
                original=runner.manifest()
                self.assertEqual(len(original['sources']),9)
                for name in sources:
                    path=here/name;before=path.read_bytes();path.write_bytes(before+b' modified')
                    self.assertNotEqual(original,runner.manifest(),name)
                    path.write_bytes(before)
                self.assertEqual(original,runner.manifest())
                plan.write_text('{"changed":true}')
                self.assertNotEqual(original,runner.manifest())
                plan.write_text('{}');workload.write_text('{"changed":true}')
                self.assertNotEqual(original,runner.manifest())

    def test_partial_final_epoch_is_never_dropped(self):
        case=mini_case(count=14)
        result=self.run_fake(case=case)
        self.assertEqual([e['prefix_count']for e in result['epochs']],[0,4,8,12,14])
        self.assertEqual(result['accepted'],14)
        self.assertEqual(len(HarnessNetwork.instances[-1].transfers),14)
        self.assertEqual(self.oracle_calls[-1],(14,'arrivals'))

    def test_zero_safety_budget_records_every_incomplete_epoch(self):
        self.small_plan['exact_total_message_safety_ceiling']=0
        result=self.run_fake()
        self.assertEqual(len(result['epochs']),4)
        self.assertTrue(all(not e['clear_result']['certified']for e in result['epochs']))
        self.assertTrue(all(e['clear_result']['status']=='incomplete'for e in result['epochs']))
        self.assertEqual(result['final']['messages'],0)
        self.assertEqual(result['accepted'],12)

    def test_control_unused_credit_carries_to_the_next_epoch(self):
        class SparseWork(HarnessNetwork):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);self.served=set()
            def clear(self,policy,budget,max_hops):
                self.clock.advance(2)
                self.calls.append(('control',policy,budget,max_hops))
                prefix=len(self.transfers)
                used=min(1,budget)if prefix not in self.served else 0
                self.served.add(prefix)
                self.messages+=used;self.delivered+=used
                return dict(used_messages=used)
        with patch.object(runner,'DecreaseFirstNetwork',SparseWork), \
             patch.object(runner,'oracle',side_effect=self.fake_oracle), \
             patch.object(runner.time,'perf_counter',HarnessNetwork.clock):
            result=runner.run_case(mini_case(),'decrease_first','arrivals',self.small_plan)
        net=HarnessNetwork.instances[-1]
        first_calls=[]
        for i,call in enumerate(net.calls):
            if i%2==0:first_calls.append(call[2])
        self.assertEqual(first_calls,[2,3,4,6])
        self.assertEqual(result['final']['messages'],4)
        self.assertEqual([e['used_messages']for e in result['epochs']],[1,1,1,1])

    @contextlib.contextmanager
    def temporary_harness_files(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);here=root/'experiments'/'mdg2';here.mkdir(parents=True)
            (root/'app').mkdir();(root/'app'/'comfort.py').write_text('economic bounds')
            sources=['exact_headroom.py','exact_headroom_benchmark.py','exact_headroom_audit.py',
                     'make_exact_headroom_workloads.py','comfort_headroom.py','comfort_decrease_first.py',
                     'comfort_curve_benchmark.py','comfort_curve_audit.py']
            for name in sources:(here/name).write_text('source '+name)
            plan=here/'plan.json';plan.write_text(json.dumps(self.plan))
            inputs=generator.build();inputs['plan_sha256']=hashlib.sha256(plan.read_bytes()).hexdigest()
            workload=here/'workload.json';workload.write_text(json.dumps(inputs))
            freeze=here/'freeze.json';output=root/'results.json'
            with patch.multiple(runner,HERE=here,ROOT=root,PLAN=plan,INPUT=workload,FREEZE=freeze):
                yield here,freeze,output

    def test_freeze_precedes_execution_cannot_overwrite_and_tampering_blocks_results(self):
        with self.temporary_harness_files()as(here,freeze,output):
            with patch.object(sys,'argv',['runner','--freeze','--output',str(output)]), \
                 patch.object(runner,'run_case',side_effect=AssertionError('must not run')), \
                 contextlib.redirect_stdout(io.StringIO()):
                runner.main()
                original=freeze.read_bytes()
                self.assertFalse(output.exists())
                with self.assertRaises(SystemExit):runner.main()
                self.assertEqual(freeze.read_bytes(),original)
            with patch.object(sys,'argv',['runner','--output',str(output)]), \
                 patch.object(runner,'run_case',side_effect=AssertionError('must not run')):
                (here/'exact_headroom.py').write_text('changed after freeze')
                with self.assertRaises(AssertionError):runner.main()
                self.assertFalse(output.exists())

    def test_campaign_retains_all_fifteen_negative_and_exhausted_rows(self):
        def fake_run(case,method,mode,plan):
            return dict(case=case['name'],profile=case['profile'],seed=case['seed'],method=method,mode=mode,
                        epochs=[dict(clearing_potential_achieved_percent=-25,
                                     clear_result=dict(status='incomplete',certified=False))],
                        final=dict(messages=0),snapshot_savings=-2)
        with self.temporary_harness_files()as(here,freeze,output):
            freeze.write_text(json.dumps(runner.manifest()))
            with patch.object(sys,'argv',['runner','--output',str(output)]), \
                 patch.object(runner,'run_case',side_effect=fake_run)as mocked, \
                 patch.object(runner,'audit_run',return_value=dict(passed=True))as audit, \
                 contextlib.redirect_stdout(io.StringIO()):
                runner.main()
            data=json.loads(output.read_text())
            self.assertTrue(data['complete'])
            self.assertEqual(mocked.call_count,15)
            self.assertEqual(audit.call_count,15)
            self.assertEqual(len(data['runs']),15)
            self.assertTrue(all(r['epochs'][-1]['clear_result']['status']=='incomplete'for r in data['runs']))
            self.assertTrue(all(r['epochs'][-1]['clearing_potential_achieved_percent']==-25 for r in data['runs']))
            self.assertEqual(len({(r['case'],r['method'],r['mode'])for r in data['runs']}),15)
            with patch.object(sys,'argv',['runner','--output',str(output)]):
                with self.assertRaises(SystemExit):runner.main()


if __name__=='__main__':unittest.main()
