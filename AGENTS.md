# Strategy Pit research collaboration

## Standing instruction: keep working

The owner asks us to keep advancing authorized node-local algorithm research, including after a failed experiment or disappointing score. Use subagents for independent implementation, mathematical review, fixtures, and validation. Keep multiple agents on useful independent tasks when such work is available, and use explicit handoffs/follow-up tasks to activate idle teammates. Do not create circular wake-up loops or busywork; agent handoffs cannot restart a stopped parent session. While this session is active, continue the next useful authorized task rather than stopping at a plan or the first benchmark. Keep the user informed and save concrete progress frequently.

Do not confuse this instruction with an ability to restart an inactive assistant. No scheduler or Goal tool was exposed when capabilities were checked in this session. Recheck available tools when resuming; this observation does not establish what a separate ChatGPT Goals feature can do. Do not promise uninterrupted work until a date, fabricate alarms, or wait idly to simulate persistence. Record blockers and exact resume commands so the next active session can continue. The owner's October 10, 2026 request was to keep working through Monday, October 12; that is a research target, not a demonstrated runtime guarantee.

Read [the research queue](docs/research-queue.md) when resuming. Check the actual repository state and saved result completion markers before rerunning work. Preserve existing user changes and agents' work. Use the existing checkout; do not create a Git worktree unless explicitly requested.

## What counts as node-local

Each participant decides using its own balances, limits, reservations, protocol state, and direct-neighbour messages. No routing or acceptance decision may inspect a global credit graph, another node's object, a simulator-wide counter, or an MCF answer. Global access is permitted for test generation, event delivery, audits and offline scoring. Label simulator-provided serialization and centrally generated starting ledgers explicitly; they do not establish a concurrent decentralized protocol.

Keep discovery, economic preferences, and settlement coordination distinct. Turn-taking on a neighbour channel is not by itself atomic settlement or optimal clearing. Distinguish message attempts, delivered application messages, duplicates, ACKs, retries and payload sizes.

## Current modeling priorities

- Timestamped Sarafu transfer replay and synthetic continuously changing graphs.
- A transaction establishes peer communication; new search cannot use a zero-balance relationship unless an explicitly named alternate policy permits it. Document any control-message grace needed to finish an in-flight transaction after a balance reaches zero.
- Dropped messages and sleeping nodes. Report pending work, blocked transfers and incomplete settlement, rather than silently counting them as successful or dropping them from denominators.
- Headroom Clearing: every original directed balance x stays in [0,B], where B is the agreed epoch ceiling; signed net positions are conserved by completed cycle moves. New external transfers change net positions and require an explicit cap-update rule.
- Local preferences and concurrency are research questions. Do not claim that original limits imply fresh consent or that a serial simulator is a fault-tolerant deployment.

## Experiments and publication

Pin source/input versions, freeze configurations before held-out tests, record actual budgets, independently replay settlements, and retain negative results. Do not call a greedy result optimal merely because its remaining positive-debt graph is acyclic: improving Headroom residual cycles may remain.

The original fixed-cap Sarafu MCF result and unlimited-credit optimum solve different models. Never compare clearing percentages without stating their input and denominator. A postpass initialized by global DFS/Jaribu is a diagnostic, not a wholly node-local pipeline.

Python tests: `/workspace/tools/strategy-pit-python/bin/python -m unittest discover -s experiments -p 'test_*.py' -q`. The environment includes OR-Tools for external references. Existing TypeScript uses Node20; separate repos may pin different versions.

The user authorized publishing the benchmark comparison, ongoing research changes and a repository-based issue tracker. Track new issues in [docs/issues](docs/issues/README.md), link them from the README, and keep status/progress current. Do not require GitHub API access to track issues in Markdown. Never bypass an automatic approval rejection or network policy; explain concrete blockers if one occurs.
