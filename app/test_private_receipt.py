import copy
import unittest
from private_node import hash_condition
from verify_private_receipt import verify


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.receipt = dict(protocol='private-hashlock-v2', hashlock_scheme='sha256-context-v2',
                            mode='testnet', unit='TEST', status='committed', local_fulfilled=True,
                            id='01'*32, preimage='02'*32, amount=3,
                            changes=[dict(peer='bob',before=-7,after=-4),dict(peer='doris',before=5,after=2)])
        self.receipt['condition'] = hash_condition(self.receipt['id'], 3, self.receipt['preimage'])

    def test_valid_raw_and_export(self):
        self.assertTrue(verify(self.receipt)['valid'])
        self.assertTrue(verify({'receipt':self.receipt})['valid'])

    def test_context_or_evidence_tampering(self):
        for key, value in [('id','03'*32), ('preimage','04'*32), ('amount',2),('unit','REAL'),('local_fulfilled',False),('condition','00'*32)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(dict(self.receipt, **{key:value}))

    def test_accounting_tampering(self):
        for field,value in [('after',3), ('after',-2), ('before',True), ('peer','bob')]:
            receipt=copy.deepcopy(self.receipt);receipt['changes'][1][field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):verify(receipt)
