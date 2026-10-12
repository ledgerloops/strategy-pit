"""Local comfort hashlock policy and immutable snapshot checks."""
import json
from pathlib import Path
import tempfile
import unittest
from comfort import comfort_move
from private_node import Node, hash_comfort_condition
from run_demo import create_configs
from verify_private_receipt import verify


class ComfortSettlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        configs=create_configs(self.tmp.name,{'alice':19001,'bob':19002,'doris':19003})
        for name,config in configs.items():
            for peer in config['peers']:
                config['peers'][peer]['balance']=-2 if (name,peer)==('alice','bob') else 2 if (name,peer)==('bob','alice') else 0
        self.nodes={name:Node(config,str(Path(self.tmp.name)/(name+'.sqlite'))) for name,config in configs.items()}
        for node in self.nodes.values():self.addCleanup(node.db.close)
        self.drain()
        for name,node in self.nodes.items():
            for peer in node.peers:
                narrow={name,peer}=={'alice','bob'}
                node.set_preferences(peer,dict(expected_revision=1,credit_limit=10,comfort_min=0 if narrow else -3,comfort_max=0 if narrow else 3,auto_adjust=True))
        self.drain()

    def entries(self):
        return [(name,dict(row)) for name,node in self.nodes.items() for row in node.db.execute('SELECT * FROM outbox')]

    def deliver(self,entry):
        sender,row=entry; self.nodes[row['peer']].receive(sender,json.loads(row['data']))
        with self.nodes[sender].db:self.nodes[sender].db.execute('DELETE FROM outbox WHERE id=?',(row['id'],))

    def drain(self):
        for _ in range(100):
            entries=self.entries()
            if not entries:return
            self.deliver(entries[0])
        self.fail('Messages did not drain')

    def settle(self):
        ident=self.nodes['alice'].discover(2,mode='comfort')['id'];self.drain()
        for node in self.nodes.values():
            data=json.loads(node.proposal(ident)['data']);node.approve(ident,data['digest'])
        self.drain()
        for node in self.nodes.values():
            self.assertTrue(verify(node.receipts()[0])['valid'])
        return ident

    def test_zero_links_and_increased_exposure_settle_with_manual_consent(self):
        ident=self.settle()
        self.assertEqual(self.nodes['alice'].balance('bob'),0)
        self.assertEqual(self.nodes['bob'].balance('doris'),2)
        self.assertEqual(self.nodes['doris'].balance('alice'),2)
        self.assertTrue(all(node.proposal(ident)['status']=='committed' for node in self.nodes.values()))

    def test_opposite_direction_and_condition_binding(self):
        for name,node in self.nodes.items():
            with node.db:node.db.execute('UPDATE balances SET balance=-balance')
        ident=self.settle()
        receipt=self.nodes['alice'].receipts()[0]
        self.assertEqual(receipt['direction'],-1)
        self.assertNotEqual(receipt['condition'],hash_comfort_condition(ident,2,receipt['preimage'],1))

    def test_stale_peer_revision_rejects_without_stuck_retry(self):
        ident=self.nodes['alice'].discover(2,mode='comfort')['id']
        bob=self.nodes['bob']
        bob.set_preferences('alice',dict(expected_revision=2,credit_limit=10,comfort_min=0,comfort_max=0,auto_adjust=False))
        self.drain()
        self.assertEqual(self.nodes['alice'].proposal(ident)['status'],'aborted')
        self.assertTrue(all(not node.db.execute('SELECT 1 FROM reservations').fetchone() for node in self.nodes.values()))

    def test_receipt_rejects_changed_policy_and_fabricated_comfort_snapshot(self):
        self.settle()
        receipt=self.nodes['alice'].receipts()[0]
        for mutate in ('direction','snapshot','permission'):
            altered=json.loads(json.dumps(receipt))
            if mutate == 'direction':altered['direction']=-altered['direction']
            elif mutate == 'snapshot':altered['changes'][0]['discomfort_after']=999
            else:
                helper=next(c for c in altered['changes'] if c['before']==0)
                helper['own_preferences']['auto_adjust']=False
            with self.assertRaises(ValueError):verify(altered)

    def test_receipt_pins_ordered_direction_quotes_and_revision_types(self):
        self.settle()
        receipt=self.nodes['doris'].receipts()[0]
        for mutate in ('reverse','quote','revision'):
            altered=json.loads(json.dumps(receipt))
            if mutate == 'reverse':
                for index,change in enumerate(altered['changes']):
                    change['after']=-change['after']
                    altered['incoming_quote' if index==0 else 'outgoing_quote']=dict(change)
            elif mutate == 'quote':altered['incoming_quote']['after']=999
            else:
                altered['changes'][0]['own_revision']=True
                altered['changes'][0]['own_preferences']['revision']=True
                altered['incoming_quote']=dict(altered['changes'][0])
            with self.assertRaises(ValueError):verify(altered)

    def test_neutral_helper_requires_both_opt_ins(self):
        own=dict(credit_limit=10,comfort_min=-3,comfort_max=3,auto_adjust=True)
        peer=dict(own,auto_adjust=False)
        self.assertFalse(comfort_move(0,2,own,peer))
        self.assertTrue(comfort_move(0,2,own,own))

if __name__=='__main__':unittest.main()
