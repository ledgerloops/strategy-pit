import numpy as np
import csv

from ortools.graph.python import min_cost_flow

# Instantiate a SimpleMinCostFlow solver.
smcf = min_cost_flow.SimpleMinCostFlow()

startArr = []
endArr = []
capArr = []
costArr = []
suppliesArr = []

# print('reading debt.csv')
with open('debt.csv', newline='') as csvfile:
    spamreader = csv.reader(csvfile, delimiter=' ', quotechar='|')
    for row in spamreader:
        startArr.append(int(row[0]) + 2)
        endArr.append(int(row[1]) + 2)
        capArr.append(float(row[2]) * 1000)
        costArr.append(1)
        suppliesArr.append(0)
        # print(', '.join(row))

source = 0
drain  = 1
flow = 10000000000000

# print('reading sources.csv')
with open('sources.csv', newline='') as csvfile:
    spamreader = csv.reader(csvfile, delimiter=' ', quotechar='|')
    for row in spamreader:
        startArr.append(source)
        endArr.append(int(row[0]) + 2)
        capArr.append(float(row[1]) * 1000)
        costArr.append(0)
        suppliesArr.append(0)
        # print(', '.join(row))
        
# print('reading drains.csv')
with open('drains.csv', newline='') as csvfile:
    spamreader = csv.reader(csvfile, delimiter=' ', quotechar='|')
    for row in spamreader:
        startArr.append(int(row[0]) + 2)
        endArr.append(drain)
        capArr.append(float(row[1]) * 1000)
        costArr.append(0)
        suppliesArr.append(0)
        # print(', '.join(row))

# Define four parallel arrays: sources, destinations, capacities,
# and unit costs between each pair. For instance, the arc from node 0
# to node 1 has a capacity of 15.
start_nodes = np.array(startArr)
end_nodes = np.array(endArr)
capacities = np.array(capArr)
unit_costs = np.array(costArr)

# Add arcs, capacities and costs in bulk using numpy.
all_arcs = smcf.add_arcs_with_capacity_and_unit_cost(
    start_nodes, end_nodes, capacities, unit_costs
)

# Add supply for each nodes.
smcf.set_nodes_supplies(np.arange(0, 2), [ flow, -flow ])

# Find the min cost flow.
status = smcf.solve_max_flow_with_min_cost()

if status != smcf.OPTIMAL:
    print("There was an issue with the min cost flow input.")
    print(f"Status: {status}")
    exit(1)
# print(f"Minimum cost: {smcf.optimal_cost()}")
# print("")
# print(" Arc    Flow / Capacity Cost")
solution_flows = smcf.flows(all_arcs)
costs = solution_flows * unit_costs
for arc, flow, cost in zip(all_arcs, solution_flows, costs):
    if flow > 0 and smcf.head(arc) != 1 and smcf.tail(arc) != 0:
        print(
            f"{(smcf.tail(arc) - 2)} {smcf.head(arc) - 2} {flow:3}"
        )
