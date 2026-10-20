"""Render exact completion and its costs from saved, independently audited runs."""
from collections import defaultdict
import csv
import html
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/mdg2-exact-headroom-2026-10-20'


def main():
    data = json.loads((OUT / 'results.json').read_text())
    assert data['complete'] and len(data['runs']) == data['expected_runs'] == 15
    rows = []
    for run in data['runs']:
        last = run['epochs'][-1]
        lengths = [len(e['receipt']['path']) for e in run['audit_events']
                   if e['kind'] == 'settlement']
        rows.append(dict(
            case=run['case'], profile=run['profile'], method=run['method'],
            mode=run['mode'], offered=run['offered'], accepted=run['accepted'],
            touched_trustlines=run['touched_trustlines'],
            final_clearing_potential_achieved_percent=last['clearing_potential_achieved_percent'],
            final_gross_debt=run['final']['gross_debt'],
            reference_gross_debt=last['oracle']['reference_gross'],
            oracle_minimum_gross_debt=last['oracle']['minimum_gross'],
            certified_epochs=sum(bool(e['clear_result']['certified']) for e in run['epochs']),
            epochs=len(run['epochs']), final_status=last['clear_result']['status'],
            messages=run['final']['messages'],
            messages_per_trustline=run['actual_messages_per_trustline'],
            json_mib=run['final']['message_bytes'] / 1048576,
            runtime_seconds=run['runtime_seconds'], loops=len(lengths),
            mean_loop_length=statistics.mean(lengths) if lengths else None,
            max_loop_length=max(lengths) if lengths else None))
    with (OUT / 'comparison.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (OUT / 'comparison.json').write_text(json.dumps(
        dict(rows=rows, plan=data['plan'], freeze=data['freeze'],
             python=data['python'], networkx=data['networkx']), indent=2) + '\n')
    grouped = defaultdict(list)
    for run in data['runs']:
        grouped[run['profile'], run['mode'], run['method']].append(run)
    aggregates = []
    for (profile, mode, method), runs in sorted(grouped.items()):
        savings = sum(r['epochs'][-1]['snapshot_savings'] for r in runs)
        potential = sum(r['epochs'][-1]['oracle']['potential'] for r in runs)
        aggregates.append(dict(
            profile=profile, mode=mode, method=method,
            achieved_percent=100 * savings / potential if potential else None,
            mean_messages_per_trustline=statistics.mean(r['actual_messages_per_trustline'] for r in runs),
            mean_runtime_seconds=statistics.mean(r['runtime_seconds'] for r in runs),
            mean_json_mib=statistics.mean(r['final']['message_bytes'] / 1048576 for r in runs),
            certified_epochs=sum(e['clear_result']['certified'] for r in runs for e in r['epochs']),
            epochs=sum(len(r['epochs']) for r in runs)))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    fig.patch.set_facecolor('#faf9f5')
    colors = {'exact': '#18705b', 'decrease_first': '#2f6fa0'}
    labels = {'exact': 'Exact residual-cycle search', 'decrease_first': 'Budgeted debt-first search'}
    for method in colors:
        runs = grouped['broad', 'arrivals', method]
        prefixes = [e['prefix_count'] for e in runs[0]['epochs']]
        achieved = []
        messages = []
        for i, _ in enumerate(prefixes):
            epochs = [r['epochs'][i] for r in runs]
            potential = sum(e['oracle']['potential'] for e in epochs)
            achieved.append(100 * sum(e['snapshot_savings'] for e in epochs) / potential
                            if potential else float('nan'))
            messages.append(statistics.mean(e['score']['messages'] / r['trustlines']
                                            for r, e in zip(runs, epochs)))
        axes[0].plot(prefixes, achieved, marker='o', color=colors[method], label=labels[method])
        axes[1].plot(prefixes, messages, marker='o', color=colors[method], label=labels[method])
    for ax in axes:
        ax.set_facecolor('#faf9f5')
        ax.set_xlabel('Transactions arrived per network')
        ax.grid(alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_ylabel('Clearing potential achieved (%)')
    finite_achieved = [e['clearing_potential_achieved_percent']
                      for run in data['runs'] if run['mode'] == 'arrivals'
                      for e in run['epochs']
                      if e['clearing_potential_achieved_percent'] is not None]
    axes[0].set_ylim(min(0, min(finite_achieved, default=0) - 2), 105)
    axes[0].axhline(100, color='#b58a42', linestyle='--', linewidth=1)
    axes[1].set_ylabel('Cumulative messages per original trustline')
    fig.suptitle('Exact clearing at frozen epoch boundaries', fontsize=19)
    fig.legend(*axes[0].get_legend_handles_labels(), loc='lower center',
               bbox_to_anchor=(.5, .075), ncol=2, frameon=False)
    fig.text(.07, .045, '3 fresh networks · 32 nodes / 96 trustlines each · 1,000 random arrivals each · broad comfort zones', fontsize=10)
    fig.text(.07, .012, 'Different budgets: exact search runs toward a certificate; control has 1,024 messages/line total. Serial research model.', fontsize=9)
    fig.subplots_adjust(left=.08, right=.98, bottom=.24, top=.87, wspace=.25)
    fig.savefig(OUT / 'exact-clearing-arrivals.png', dpi=200)
    fig.savefig(OUT / 'exact-clearing-arrivals.svg')
    plt.close(fig)
    table = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(value))}</td>' for value in [
        r['profile'], r['mode'], r['method'],
        f'{r["achieved_percent"]:.2f}%' if r['achieved_percent'] is not None else 'Undefined',
        f'{r["mean_messages_per_trustline"]:.1f}', f'{r["mean_json_mib"]:.2f}',
        f'{r["mean_runtime_seconds"]:.3f}', f'{r["certified_epochs"]}/{r["epochs"]}']) + '</tr>'
                    for r in aggregates)
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Exact node-local headroom clearing</title>
<style>body{{font:16px/1.5 system-ui;max-width:1150px;margin:40px auto;padding:0 24px;color:#233d31}}img{{width:100%}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:7px;border-bottom:1px solid #ccc;text-align:left}}code{{overflow-wrap:anywhere}}</style>
<h1>Exact node-local residual-cycle clearing</h1>
<p>20 October 2026. Fresh synthetic seeds 501–503; each network has 32 nodes and 96 original undirected trustlines. Research implementation; no app or demo configuration changes.</p>
<p>The objective is 100% of feasible clearing potential, not enumeration of every possible loop. Loops overlap, and settling one changes what remains. The exact mode seeks a negative-cost residual cycle, settles one unit with bilateral comfort checks, and repeats until a completion certificate or the safety ceiling.</p>
<img src="exact-clearing-arrivals.png" alt="Clearing potential and communication after each batch of 100 arrivals">
<h2>Measured results</h2>
<table><tr><th>Comfort</th><th>Mode</th><th>Method</th><th>Potential achieved</th><th>Messages/line</th><th>JSON MiB</th><th>Actor runtime s</th><th>Certified epochs</th></tr>{table}</table>
<p>Percentages pool savings and potential across three seeds; costs are means per network. Communication includes search and settlement. Runtime is one illustrative sample per run, summing network construction, transfer processing and clearing; offline oracle, audit and result serialization are excluded.</p>
<h2>Heavier arrivals and fair interpretation</h2>
<p>Each broad-zone arrival run receives 1,000 transfers: the first 1,000 events of a Poisson process at rate 25 per simulated time unit, uniform original trustlines, signed amounts ±1, ±2 or ±3. All 96 trustlines receive arrivals in each network. Clearing occurs initially and after each 100 arrivals, for 11 frozen epochs. Arrivals are buffered during service. This measures complete epoch snapshots, not real-time throughput or completion while balances are changing.</p>
<p>Exact mode has a 2,000,000-message total safety ceiling per run. The existing debt-first control has 1,024 messages per trustline total, spread across the same epochs with unused credit carried. These are deliberately different stopping rules: the table exposes the price of a certificate rather than claiming a matched-budget speedup. Budget exhaustion is retained as incomplete.</p>
<p>For every epoch, replay the same accepted transaction prefix without clearing to obtain gross debt D; an offline hard-bound min-cost flow gives D*. Potential achieved is (D−actual debt)/(D−D*). This is snapshot saving, not cumulative settled volume. Initial gross debt plus absolute offered volume is below the generous 10,000-unit hard grants, ensuring every offered transfer is feasible in both models.</p>
<h2>What makes completion possible</h2>
<p>Actors use their own bilateral state and direct-neighbour messages. Distributed Bellman–Ford searches replace randomized path sampling. An explicitly coordinated epoch holds balances fixed, chooses one discovered cycle, and completes staged prepare/commit/cleanup before searching again. Setup, search coordination and settlement traffic are counted. Network size and a fixed coordinator are supplied; reliable delivery and synchronous service are simulator assumptions.</p>
<p>The coordinator decides from counted tree reports and received cycle witnesses. The full collection of node potentials and incidence checks is exported separately by the simulator for independent audit; that global audit export is not an actor's routing input. The final counted certificate broadcast announces completion, rather than distributing this entire audit artifact.</p>
<p>With broad zones equal to hard bounds and bilateral helper consent, no negative residual cycle is the optimality condition for the minimum-gross-debt flow. Integer unit improvements make progress finite. The underlying min-cost-flow criterion is described in <a href="https://courses.csail.mit.edu/6.854/17/Scribe/s11-minCostFlow.html">MIT's cycle-cancellation notes</a>; adapting it to these local messages and comfort rules is this experiment's implementation and proof obligation.</p>
<p>Narrow zones can deny required helper moves. A certificate then means no currently admissible improving unit cycle; it does not establish the hard-limit optimum or the best outcome reachable through all possible earlier comfort choices. The percentage denominator remains the relaxed hard-limit ceiling.</p>
<h2>Requirements beyond this prototype</h2>
<p>A live deployment needs agreed membership or sound distributed termination detection, versioned snapshots or reservations against arriving transfers, durable settlement and recovery under failures, and a communication protocol that meets the app's privacy requirements. Current search tokens disclose paths; this is not the neighbour-private hashlock protocol. The epoch coordinator selects only from received witnesses, but its scheduling and reliability remain explicit research assumptions.</p>
<p>Worst-case cost can be high: complete cycle searches require communication across the network, and unit settlement may repeat many times. Batching safe amounts and reusing search information are performance opportunities that would need separate correctness checks.</p>
<h2>Reproduction and audit</h2>
<p>Python {data['python']}, NetworkX {data['networkx']}; exact source, plan and workload hashes in <a href="comparison.json">comparison.json</a>. All completed settlements and offered transfers are retained for independent replay; every claimed broad optimum is checked against a separately certified oracle and residual certificate.</p>
<p><a href="results.json">Raw measurements</a> · <a href="comparison.csv">CSV</a> · <a href="independent-audit.json">Independent audit</a> · <a href="REPRODUCE.txt">Reproduce</a></p></html>'''
    (OUT / 'report.html').write_text(page)
    print(json.dumps(aggregates, indent=2))


if __name__ == '__main__':
    main()
