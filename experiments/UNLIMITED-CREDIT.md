# Unlimited credit between existing neighbors

Interpret the rule “each node keeps the same total debt summed over its neighbors” as preserving its **signed net position**: receivables minus payables. That is a sound accounting constraint and is already preserved by cycle updates. It does not specify a preference by itself: many arrangements preserve net positions. This experiment retains the objective of minimizing gross bilateral debt, `sum(abs(balance))` over unordered pairs.

If instead every node must preserve the sum of *absolute* incident balances, global gross debt cannot decrease: the sum of those node totals is exactly twice gross bilateral debt. Likewise, preserving every node's total payable amount fixes the global sum of obligations. These are different rules from signed-net conservation.

## Full Sarafu calculation

Use the same pinned, bilaterally netted Sarafu debt graph as the original comparison:

- Commit `06c6a2fb5702c7066ded7cf14672ba07ed5098c4`.
- 37,677 nodes and 94,223 existing neighbor pairs.
- Initial gross debt: **107,886,628.824** accounting units.
- Fixed sum of positive net positions: **16,961,471.329** units.
- No additional neighbor pairs are introduced. Both directions on every existing pair have unlimited credit.

| Feasible model | Optimal remaining gross debt | Optimal reduction |
| --- | ---: | ---: |
| Original: only reduce existing debts | 35,214,739.210 | **67.3595%** |
| Unlimited bilateral credit, same neighbors | 26,874,197.893 | **75.0903%** |
| Counterfactual: everyone can directly trust everyone | 16,961,471.329 | **84.2784%** |

The first two are fresh OR-Tools solves that returned `OPTIMAL`. The third is an analytical lower bound attained with a complete graph; it was not obtained by adding a quadratic number of edges and running that enormous graph. It assumes *new* counterparty relationships and is not the user's existing-neighbor rule.

Unlimited neighbor credit improves clearing by **7.7308 percentage points**, or **8,340,541.317** additional units, over cancellation-only clearing. In the particular optimal solution returned, 11,174 existing-direction debts increase and 2,705 original debts reverse direction. These counts describe one optimum, not necessarily all optimal arrangements. All node net positions and neighbor pairs are independently checked in the solver wrapper.

This is a fictitious debt graph derived from historical Sarafu transfers. It is not a measurement of actual participants' credit preferences. Its neighbor pairs come from **nonzero net debt edges**: historical relationships that netted to zero are absent from this file. Allowing those additional historical relationships could change the answer.

## Why unlimited credit does not clear everything

Preserving signed net positions leaves net debtors and creditors. A net debtor's obligation must reach a net creditor through existing neighbor links. If that requires three links, one unit of net debt contributes three units to the gross bilateral total.

With unlimited capacities, the optimization becomes a transport problem over graph distances: match net debtors with net creditors while minimizing the total amount times route length. A chain `A owes B 3; B owes C 3` still has gross debt 6 if A and C are not neighbors. On a tree, node net positions uniquely determine every edge balance, so unlimited credit alone gives no freedom to improve it.

For this Sarafu graph, the optimal gross total is about **1.5844 times** the fixed net debt. In a complete graph each required obligation could be a direct debtor-to-creditor relationship, making that factor 1 and attaining the 84.2784% counterfactual ceiling. Infinite trust in existing neighbors does not create those direct relationships.

## Exact formulation

Input `debt.csv` is debtor-to-creditor positive flow. Its outgoing-minus-incoming sum is the node's net debt, the negative of the creditor-positive balance convention in `trustlines.py`. The two conventions encode the same conserved positions.

For unlimited credit, give each undirected neighbor pair two directed arcs of cost +1, with the original node net debts as supplies/demands. Positive costs eliminate opposing flows and unnecessary directed circulations at an optimum; the resulting objective is exactly gross bilateral debt.

“Infinite” capacity can be represented exactly by the total positive net supply `N`. An optimal positive-cost flow decomposes into source-to-sink paths totaling N, so no arc needs capacity greater than N. This is a bound on an optimal solution, **not a bound that must contain the initial balances**: the initial graph can contain large circulations even when N is small or zero. The tests explicitly cover this distinction.

The cancellation-only comparison instead gives each original directed edge its original balance as capacity and adds no reverse arcs. Both solves preserve every node's position. The input parser rejects reciprocal debts and requires bilateral netting first, so the comparison does not accidentally count ordinary bilateral cancellation as a benefit of extra credit.

## Interpretation and next step

As an economic assumption, unlimited neighbor trust means accepting arbitrarily redistributed counterparty exposure under the agreed net-preservation rule. A node's total receivables and payables can both grow while its net position remains the same. If that is acceptable by assumption, the model is internally consistent. If nodes care about their gross exposure or counterparty mix, those preferences require additional constraints or costs.

The optimum gives a reference target for future distributed trustline search. It does not establish that the existing neighbor-message DFS prototype reaches it, or supply a distributed protocol for agreeing to and executing signed updates.

## Reproduce

Using the optional OR-Tools environment from [README.md](README.md):

```sh
experiments/.venv/bin/python experiments/unlimited_credit.py
experiments/.venv/bin/python -m unittest discover -s experiments -p 'test_unlimited_credit.py' -v
```

The script overwrites `results/unlimited-credit.json` by default; pass `--output` to choose another file. It records the exact input commit/hash, source hashes, solver version, amounts, objective values, and validation flags. Tests include tree/path distance, introducing an extra neighbor, initial circulations larger than the exact supply cap, zero net supply, disconnected components, and exhaustive small triangle balance states.
