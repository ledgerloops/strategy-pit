import unittest
from headroom_floor_reference import floor_reference


class FloorReferenceTests(unittest.TestCase):
    def test_unit_triangle_completely_blocked(self):
        graph={(0,1):1,(1,2):1,(2,0):1}
        self.assertEqual(floor_reference(graph,0)['minimum_final_debt_scaled'],0)
        self.assertEqual(floor_reference(graph,1)['minimum_final_debt_scaled'],3)

    def test_shared_return_amplifies_floor_cost(self):
        # k=10 branches, L=10 return edges: 30 edges but 120 units trapped.
        graph={}
        for i in range(2,12):
            graph[0,i]=graph[i,1]=1
        path=[1]+list(range(12,21))+[0]
        graph.update({edge:10 for edge in zip(path,path[1:])})
        self.assertEqual(len(graph),30)
        self.assertEqual(floor_reference(graph,0)['minimum_final_debt_scaled'],0)
        self.assertEqual(floor_reference(graph,1)['minimum_final_debt_scaled'],120)

    def test_nonzero_net_positions_survive_shift(self):
        graph={(0,1):7,(1,2):5,(2,0):3}
        self.assertEqual(floor_reference(graph,0)['minimum_final_debt_scaled'],6)
        self.assertEqual(floor_reference(graph,1)['minimum_final_debt_scaled'],9)
        with self.assertRaises(ValueError): floor_reference(graph,4)

if __name__=='__main__': unittest.main()
