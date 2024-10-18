# LedgerLoops Strategy Pit

This repository is an experimentation ground for LedgerLoops strategies.

## Sarafu-Based Netting Challenge
This challenge compares cycle detection algorithms in two categories: centralised and decentralised.

A centralised algorithm is allowed to base its next step on global state, whereas in a decentralised one steps can only be taken based on state that is available in a single network node after this node has exchanged messages with only its direct neighbours in the graph.

### Full Run
To run DFS and MCF+DFS and compare their performance, do the following:
```
npm install
python -m pip install ortools
npm run build
node ./build/src/sarafu-to-debt.js ../Sarafu2021_UKdb_submission/sarafu_xDAI/sarafu_txns_20200125-20210615.csv ./debt.csv ./sources.csv ./drains.csv 1000000
python mcf.py > flow.csv
node build/src/subtractFlow.js ./debt.csv ./flow.csv ./mcf-out.csv
node build/src/dfs.js debt.csv dfs.csv
node build/src/dfs.js mcf-out.csv mcf-dfs.csv
node ./build/src/analyse-sarafu-challenge-solution.js ./debt.csv ./dfs.csv
node ./build/src/analyse-sarafu-challenge-solution.js ./debt.csv ./mcf-dfs.csv
```
You'll see MCF+DFS nets 67% of debt and DFS by itself only nets 60% of debt, so it's underperforming by about 10%.

### Input data
The Sarafu Netting Challenge uses the transaction data from the [Sarafu Community Inclusion Currency, 2020-2021](https://www.nature.com/articles/s41597-022-01539-4) which is available for download free of charge from [UK Data Service](https://beta.ukdataservice.ac.uk/datacatalogue/studies/study?id=855142). To obtain the dataset you may be able to use your existing academic credentials, or you may need to create an account and wait a few days for it to be activated. The download will contain a folder named `Sarafu2021_UKdb_submission` which contains a folder named `sarafu_xDAI`, which contains a file named `sarafu_txns_20200125-20210615.csv`. It is this CSV file that will be used as an input here.

### Debt Graph Construction
The input for this challenge is a fictitious debt graph that is constructed from some real transaction data. Even though we use real transaction data, the setting is still fictitious.

In reality, the Sarafu dataset contains three types of transactions: disbursement, standard and reclamation, and these transactions all really happened during 2020-2021.

In a disbursement, Sarafu is added to a user's account. A standard transaction transfers Sarafu from one user to another. And in a reclamation, Sarafu is removed from a user's account.

We look only at the standard transactions, and instead of treating them as payments in exchange for something, we pretend that they adjust bilateral balances.

This way we construct a weighted, directed graph in which the weight of an edge from A to B is equal to the sum of the amounts of the transfers that went from A to B, minus the sum of the amounts of transfers that went from B to A.

To generate `./debt.csv` (and also `sources.csv` and `drains.csv` helper files for `mcf.py`), run:
```
npm install
npm run build
node ./build/src/sarafu-to-debt.js ../Sarafu2021_UKdb_submission/sarafu_xDAI/sarafu_txns_20200125-20210615.csv ./debt.csv ./sources.csv ./drains.csv
```

### Initial analysis
As the `sarafu-to-debt.js` script will output, the debt graph after bilateral netting contains 94,223 non-zero balances between 37677 accounts.
The [Net Internal Debt](https://cycles.money/blog/obligation-clearing-algorithm-design-101) after bilateral netting is around 17 million Sarafu.
That is around 16 percent of the total of around 108 million Sarafu in bilateral balances.

## Solution Format
A solution consists of a CSV file, where each line contains a space-delimited list of 3 or more node numbers, followed by an amount, e.g.:

```
8 5 21 3 5.3
43 2 6 3 7 62
```

This solution consists of two netting agreements, one for cycle 8 -> 5 -> 21 -> 3 -> 8 with amount 5.3 Sarafu, and the other for cycle 43 -> 2 -> 6 -> 3 -> 7 -> 43 with amount 62.

A cycle [node_0, node_1, ..., node_n, amount] is nettable if its amount positive but smaller than each of the balances it traverses, that is to say, for each k such that 0 <= k <= n-1, graph[cycle[k] cycle[k+1]] > amount, and additionally for the last step that closes the cycle, graph[cycle[n] cycle[0]] > amount. So given the following debt graph:
```
8 5 20
5 21 543
21 3 12
3 8 100
```
with net positions:
8: -100 + 20 = -80
5: -20 + 543 = 523
21: -543 + 12 = -531
3: -12 + 100 = 88
and NID of (80+531) = (523+88) = 611,
the cycle `8 5 21 3 5.3` is nettable and would result in a graph:
```
8 5 14.7
5 21 537.7
21 3 6.7
3 8 94.7
```
with the same net positions and NID as before.

## Solution Analysis
To analyse a solution, save it a for instance `solution.csv` and run:
```
node ./build/src/analyse-sarafu-challenge-solution.js ./debt.csv ./solution.csv
```

# Contestants
## Depth First Search ('DFS')
This centralized algorithm does a repeated depth-first search, stringing together paths through the graph similar to the 'Snake' game that was popular on feature phones in the 1990s.
```
node build/src/dfs.js
```

## MCF+DFS
We run a minimum-cost flow algorithm in python, followed by BEW, which leads to a slightly better performance:
```
python -m pip install ortools
python mcf.py
node build/src/dfs.js mcf-out.csv
```
