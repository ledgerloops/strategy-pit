import tempfile
from pathlib import Path
import unittest

from temporal_sarafu import Transfer, load_sarafu, net_graph

HEADER = 'id,timeset,transfer_subtype,source,target,weight,token_name,token_address\n'


class TemporalSarafuTests(unittest.TestCase):
    def load(self, rows, **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.csv'
            path.write_text(HEADER + '\n'.join(rows) + '\n')
            return load_sarafu(path, **kwargs)

    def test_sort_exact_time_ties_scale_and_historical_peer_ids(self):
        fixture = self.load([
            '1,2020-01-01 00:00:00,DISBURSEMENT,bank,a,99,Sarafu,token',
            '2,2020-01-01 00:00:02.100001,STANDARD,b,a,1.005,Sarafu,token',
            '3,2020-01-01 00:00:01.100000,STANDARD,a,b,2,Sarafu,token',
            '4,2020-01-01 00:00:02.100001,STANDARD,a,b,0.005,Sarafu,token',
        ])
        self.assertEqual(fixture.events, (Transfer(0, 3, 4, 2000, 4),
                                          Transfer(1, 4, 3, 1005, 3),
                                          Transfer(1, 3, 4, 5, 5)))
        self.assertFalse(fixture.metadata['csv_chronological'])
        self.assertEqual(net_graph(fixture.events), {(3, 4): 1000})
        self.assertIsNone(fixture.metadata['source_commit'])

    def test_zero_closes_and_later_transfer_reopens_with_reversed_debt(self):
        events = [Transfer(0, 1, 2, 7000), Transfer(1, 2, 1, 7000),
                  Transfer(2, 2, 1, 3000)]
        self.assertEqual(net_graph(events[:1]), {(1, 2): 7000})
        self.assertEqual(net_graph(events[:2]), {})
        self.assertEqual(net_graph(events), {(2, 1): 3000})
        self.assertEqual(net_graph([Transfer(0, 1, 1, 9000)]), {})

    def test_microsecond_clock_does_not_round_through_float(self):
        fixture = self.load([
            '1,2020-01-01 00:00:00.000001,STANDARD,a,b,1,Sarafu,token',
            '2,2020-01-02 00:00:00.000002,STANDARD,b,a,1,Sarafu,token',
        ], tick_microseconds=1)
        self.assertEqual(fixture.events[-1].time, 86400000001)

    def test_unrepresentable_and_negative_amounts_are_rejected(self):
        for amount in ('0.0001', '-1', 'NaN', 'Infinity'):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.load([f'1,2020-01-01,STANDARD,a,b,{amount},Sarafu,token'])

    def test_bad_clock_and_empty_standard_stream(self):
        with self.assertRaises(ValueError):
            self.load([], tick_microseconds=0)
        fixture = self.load(['1,2020-01-01,DISBURSEMENT,a,b,1,Sarafu,token'])
        self.assertEqual(fixture.events, ())
        self.assertIsNone(fixture.metadata['first_standard'])
        self.assertEqual(fixture.metadata['final_bilateral_debt_scaled'], 0)


if __name__ == '__main__':
    unittest.main()
