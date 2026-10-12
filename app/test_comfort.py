"""Bilateral preference model and durable local consent boundary checks."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from comfort import validate_preferences, shared_comfort, allows_balance
from private_node import Node, PROTOCOL
from run_demo import create_configs


def pref(limit=10, low=-10, high=10, auto=False):
    return dict(credit_limit=limit,comfort_min=low,comfort_max=high,auto_adjust=auto)


class ComfortModelTests(unittest.TestCase):
    def test_peer_interval_is_mirrored_then_clipped(self):
        self.assertEqual(shared_comfort(pref(8,-7,9),pref(5,-4,6)),dict(hard_min=-5,hard_max=8,min=-5,max=4,empty=False))
        opposite=shared_comfort(pref(5,-4,6),pref(8,-7,9))
        self.assertEqual((opposite['min'],opposite['max']),(-4,5))

    def test_disjoint_comfort_is_explicit(self):
        result=shared_comfort(pref(20,3,5),pref(20,3,5))
        self.assertTrue(result['empty'])
        self.assertGreater(result['min'],result['max'])

    def test_lowered_limits_allow_reduction_without_erasing_debt(self):
        own,peer=pref(2),pref(3)
        self.assertTrue(allows_balance(9,8,own,peer))
        self.assertTrue(allows_balance(-9,-8,own,peer))
        self.assertFalse(allows_balance(9,10,own,peer))
        self.assertFalse(allows_balance(-9,-10,own,peer))
        self.assertFalse(allows_balance(1,-4,own,peer))
        self.assertTrue(allows_balance(1,-3,own,peer))

    def test_bad_types_and_ranges_rejected(self):
        for field,value in [('credit_limit',-1),('credit_limit',True),('comfort_min',1.5),('comfort_max',10**13),('auto_adjust',1)]:
            bad=pref();bad[field]=value
            with self.assertRaises(ValueError):validate_preferences(bad)
        with self.assertRaises(ValueError):validate_preferences(pref(low=2,high=1))


class ComfortStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        configs=create_configs(self.tmp.name,{'alice':19901,'bob':19902,'doris':19903})
        self.nodes={name:Node(config,str(Path(self.tmp.name)/(name+'.sqlite'))) for name,config in configs.items()}
        for node in self.nodes.values():self.addCleanup(node.db.close)
        self.drain()

    def drain(self):
        for _ in range(100):
            deliveries=[(name,dict(row)) for name,node in self.nodes.items() for row in node.db.execute('SELECT * FROM outbox')]
            if not deliveries:return
            for name,row in deliveries:
                self.nodes[row['peer']].receive(name,json.loads(row['data']))
                with self.nodes[name].db:self.nodes[name].db.execute('DELETE FROM outbox WHERE id=?',(row['id'],))
        self.fail('Outbox did not drain')

    def test_initial_sync_and_updates_are_bilateral(self):
        alice=self.nodes['alice'];before=alice.balance('bob')
        self.assertTrue(all(c['peer_preferences'] for c in alice.contacts()))
        saved=alice.set_preferences('bob',dict(pref(8,-4,3,True),expected_revision=1))['contact']
        self.assertEqual(saved['own']['revision'],2)
        self.assertFalse(saved['auto_adjust_active'])
        self.drain()
        bob=next(c for c in self.nodes['bob'].contacts() if c['peer']=='alice')
        self.assertEqual(bob['peer_preferences']['credit_limit'],8)
        self.assertEqual(alice.balance('bob'),before)
        self.assertEqual(next(c for c in alice.contacts() if c['peer']=='doris')['own']['revision'],1)
        with self.assertRaises(ValueError):alice.set_preferences('bob',dict(pref(),expected_revision=1))

    def test_stale_and_conflicting_peer_revisions(self):
        node=self.nodes['alice']
        def send(revision,limit):
            node.receive('bob',dict(kind='preferences',protocol=PROTOCOL,message_id=uuid.uuid4().hex,preferences=dict(pref(limit),revision=revision)))
        send(3,4);send(2,6);send(3,4)
        contact=next(c for c in node.contacts() if c['peer']=='bob')
        self.assertEqual(contact['peer_preferences']['credit_limit'],4)
        with self.assertRaises(ValueError):send(3,9)

    def test_reservations_pin_preferences_until_abort(self):
        alice=self.nodes['alice'];ident=alice.discover(3)['id'];self.drain()
        with self.assertRaises(ValueError):alice.set_preferences('bob',dict(pref(),expected_revision=1))
        message=dict(kind='preferences',protocol=PROTOCOL,message_id=uuid.uuid4().hex,preferences=dict(pref(2),revision=2))
        with self.assertRaises(ValueError):alice.receive('bob',message)
        data=json.loads(alice.proposal(ident)['data']);alice.decline(ident,data['digest']);self.drain()
        alice.receive('bob',message)
        self.assertEqual(next(c for c in alice.contacts() if c['peer']=='bob')['peer_preferences']['revision'],2)

    def test_lowered_cap_does_not_block_canceling_existing_exposure(self):
        for node in self.nodes.values():
            for peer in node.peers:node.set_preferences(peer,dict(pref(0,0,0),expected_revision=1))
        self.drain()
        ident=self.nodes['alice'].discover(3)['id'];self.drain()
        for node in self.nodes.values():
            data=json.loads(node.proposal(ident)['data']);node.approve(ident,data['digest'])
        self.drain()
        self.assertTrue(all(node.proposal(ident)['status']=='committed' for node in self.nodes.values()))
        self.assertEqual(self.nodes['alice'].balance('bob'),-4)

if __name__=='__main__':unittest.main()
