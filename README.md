# LedgerLoops Strategy Pit

This repository is an experimentation ground for LedgerLoops strategies.

## Sarafu-Based Netting Challenge
This challenge compares cycle detection algorithms in two categories: centralised and decentralised.

A centralised algorithm is allowed to base its next step on global state, whereas in a decentralised one steps can only be taken based on state that is available in a single network node after this node has exchanged messages with only its direct neighbours in the graph.

### Full Run
To run DFS and MCF+DFS and compare their performance, do the following:
```
npm install
npm run build
node ./build/src/sarafu-to-debt.js ../Sarafu2021_UKdb_submission/sarafu_xDAI/sarafu_txns_20200125-20210615.csv ./debt.csv ./sources.csv ./drains.csv
python -m pip install ortools
python mcf.py > flow.csv
node build/src/subtractFlow.js ./debt.csv ./flow.csv ./mcf-out.csv
node build/src/dfs.js debt.csv dfs.csv
node build/src/dfs.js mcf-out.csv mcf-dfs.csv
node ./build/src/analyse-sarafu-challenge-solution.js ./debt.csv ./dfs.csv
node ./build/src/analyse-sarafu-challenge-solution.js ./debt.csv ./mcf-dfs.csv
```
You'll see MCF+BEW nets ??% of debt and DFS by itself only nets ??% of debt, so it's underperforming by ??%.

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


# Older Experiments
## Usage
```
npm install
npm test
npm run build
node ../ledgerloops/src/network-generator.js > __tests__/fixtures/testnet.csv
time node ./build/src/run.js
```

## Network simulators
See also 2024 work on ngraph generator in [ledgerloops/ledgerloops repo](https://github.com/ledgerloops/ledgerloops).
To import the first 20 lines of Sarafu data, run `node ./sarafu.js`. This network should have 3 loops that compete to clear 6 -[.5]-> 4:
* 4 -[323]-> 6 -[.5]-> 4
* 4 -[2]-> 3 -[123]-> 6 -[.5]-> 4
* 4 -[10]-> 7 -[12]-> 3 -[123]-> 6 -[.5]-> 4

### Basic
In the basic network simulator, nodes Alice and Bob can become neighbours with:
```js
const alice = new Node('alice');
const bob = new Node('bob');
alice.meet(bob);
```
After that, Alice can contact Bob, for instance with a `Meet` message:
```js
class MyStrategy extends Node {
  meet(other: Node): void {
    this.addFriend(other);
    other.receiveMessage(new Meet(this));
  }
  receiveMessage(sender: string message: Message): void {
    if (message.getMessageType() === `meet`) {
      this.addFriend(sender);
    }
  }
}
```
The `Meet` message will give Bob a handle to Alice, so now they can send each other
any message they want:
```js
bob.receiveMessage(this, new Probe('435af3b4'));
```
A `Node#receiveMessage` call may trigger other messages to be sent, so make sure that this doesn't get into an infinite loop.
This in itself means that this network simulator is not Byzantine fault tolerant, because nodes have infinite patience in this model.
Only one node is acting at a time, and while it is acting, all other nodes are completely asleep until the acting node responds.

### Message ticks
The message ticks model (not implemented yet) improves upon the basic network simulator in that each node gets a change to execute on each clock tick,
and messages sent during clock tick `n` will be delivered in clock tick `n+1`.
Each node is allowed to act on each of the events that have been queued up for it (messages or otherwise), for unlimited time, so if one node gets into an infinite loop
or long sleep, all other nodes will sleep too.

### Message ticks with timeouts
The message ticks with timeouts model (not implemented yet) improves upon the message ticks network simulator in that on each clock tick, each node is allowed to act on each of the events that have been queued up for it (messages or otherwise), for up to a set limit (e.g. 1000ms per event).

## Network Topologies
### Triangle
The simplest network topology has 3 nodes (Alice, Bob and Charlie), and its links evolve as follows:
1. None.
2. Alice->Bob.
3. Alice->Bob, Bob->Charlie.
4. Alice->Bob, Bob->Charlie, Charlie->Alice.

### Hour Glass
This network topology has 5 nodes (Alice, Bob, Charlie, Dave and Edward), and its links evolve as follows (Alice is at the center where two triangles meet):
1. None.
2. Alice->Bob.
3. Alice->Bob, Bob->Charlie.
4. Alice->Bob, Bob->Charlie, Charlie->Alice.
5. Alice->Bob, Bob->Charlie, Charlie->Alice, Alice->Dave.
6. Alice->Bob, Bob->Charlie, Charlie->Alice, Alice->Dave, Dave->Edward.
7. Alice->Bob, Bob->Charlie, Charlie->Alice, Alice->Dave, Dave->Edward, Edward->Alice.

## Current Strategies

###  <img src="./img/giraffe.png" style="width:100px;border-radius: 10px"/> Giraffe
The Giraffe is the first strategy to properly detect Kite Loops, see https://github.com/ledgerloops/strategy-pit/issues/15.

###  <img src="./img/saiga.png" style="width:100px;border-radius: 10px"/> Saiga
The Saiga differs from the Giraffe in that it negotiates pegged loops (no exchange rates), see https://github.com/ledgerloops/strategy-pit/issues/24.

###  <img src="./img/badger.png" style="width:100px;border-radius: 10px"/> Badger
The Badger differs from the Saiga in that it uses majority-based all-or-nothing finality, see https://github.com/ledgerloops/strategy-pit/issues/29.

## Second Generation Strategies
###  <img src="./img/stingray.png" style="width:100px;border-radius: 10px"/> Stingray
The Stingray has a more detailed data storage (both for Flood Probes and for Trace Probes) than its predecessors Salmon, Pelican and Petrogale.
A Stingray reacts to events with actions. Events are:
* Meet - a new neighbour is added. Although neighbour links are symmetrical, the Meet event is triggered in only one of the two parties
* Receiving a Meet message (being the other party in a Meet)
* Receiving a Probe message from a neighbour
* Receiving a Trace message from a neighbour

Actions are:
* Mint a probe and send it to one or more neighbours
* Forward an incoming probe to one or more neighbours
* Mint a Trace and send it to a neighbour
* Forward an incoming Trace to a different neighbour
* Conclude that a loop exists

A Stingray will behave as follows:
For every Meet, mint a probe and send it to all neighbours (including the new one)
For every incoming probe:
* if it is unknown, forward it to all other neighbours (not including the sender)
* if it is known, home-minted and *virgin for that sender* (see below), mint a trace and send that to just the sender of the probe
* in all other cases (i.e. known but not home-minted and/or not virgin for the sender), mint a probe and send that to just the sender of the probe (we call this is a "pinning probe")
For every incoming trace:
* if it was home-minted, conclude that a loop exists
* if it was not home-minted, look at the Probe ID it relates to, and forward it to the neighbour who originally sent you that probe (a Trace backtraces a probe).

A Probe is *virgin* for a neighbour if it was never sent to them and never received from them.

###  <img src="./img/jackal.png" style="width:100px;border-radius: 10px"/> Jackal
Same as Stingray except that, as a mitigation for https://github.com/ledgerloops/strategy-pit/issues/7, the other node is told to pauze its messages during the batch of messages that are triggered by an `onMeet` event.

###  <img src="./img/squid.png" style="width:100px;border-radius: 10px"/> Squid
Same as Jackal except that, in consideration of https://github.com/ledgerloops/strategy-pit/issues/8, of the two nodes in a neighbour relationship, one unpauzes whenever the other one pauzes.

## First Generation Strategies
### <img src="./img/salmon.png" style="width:100px;border-radius: 10px"/> Salmon

The Salmon strategy works as follows:
When a Salmon Node meets a new node, it:
* adds this node as a contact
* sends that new a Meet message
* mints a new Probe message
* sends it to all
* considers its chronological list of contacts (including the new one)
* sends the probe to the oldest contact
* unless this results in a loop being found from this probe, sends it to the next contact in the list
* repeat for all contacts in the list (including the new one)

When a Salmon Node receives a Meet message:
* add this node as a contact
* deduplicate on `node->getName()`
* throw an error in case a contact by that name already exists)

When a Salmon Node receives a Probe message:
* store it
* deduplicate on Probe Id
* if a probe by this Probe Id already exists, conclude that a loop is found (see below)
* else forward this probe to all other contacts

When a Salmon Node finds a loop:
* send a Loop message for this loop's Probe Id to all contacts
* mark this loop as known (deduplicate on Probe Id)

When a Salmon Node receives a Loop message:
* if it is already marked as known, do nothing
* otherwise, mark it as known, and
* forward it to all other contacts (note that this is a bug, see below)

Three Salmons in a Triangle in the Basic simulator will successfully find three loops.
They will not be able to detect that the three loops have exact overlap.
They rely on the fact that a triangle has no forks.
Forwarding a Loop message to all other contacts is a bug unless the number of other contacts is exactly one. This bug goes undetected in the Triangle topology, but Salmon loop detection would break if you put them in an Hourglass topology.

Also, Salmons don't implement exchange rate negotiation.

### <img src="./img/pelican.png" style="width:100px;border-radius: 10px"/> Pelican

Pelicans differ from Salmons in that they create multiple Loops per Probe - forking them whenever the network forks. This means they can handle not only the Triangle but also the Hourglass topology.

Due to a bug in a mechanism that was meant to prevent unnecessary probes to a newly met node, nodes in the second triangle
don't get to see all the probes and loops.

###  <img src="./img/petrogale.png" style="width:100px;border-radius: 10px"/> Petrogale

The Petrogale is identical to the Pelican except that it always sends all existing probes to a newly met node, even if
loops were already found for them.

I think in the hourglass test, the first triangle is found 3 times and the second triangle is found 8 times, although it's
hard to tell because of #1 and #2.

###  <img src="./img/butterfly.png" style="width:100px;border-radius: 10px"/> Butterfly
The Butterfly uses:
* [Polite Messaging](https://github.com/ledgerloops/strategy-pit/issues/8) for Probes to avoid losing a chance for proof of communication due to probes crossing over
* Flood probes in both directions when a new link is added
* An additional Flood probe ([pinned](https://github.com/ledgerloops/strategy-pit/issues/5)) when a probe loops back to a forwarder instead of to the root
* A Trace probe in the opposite direction when a Flood probe loops back to the root
