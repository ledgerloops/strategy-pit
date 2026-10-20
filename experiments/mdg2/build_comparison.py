"""Audit and render the MDG2 benchmark artifacts without rerunning the measurements."""
from collections import defaultdict, Counter
import csv
import hashlib
import html
import json
from pathlib import Path
import platform
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/mdg2-2026-10-25'
WORKLOAD = Path(__file__).with_name('workloads.json')
LABELS = {'random':'LedgerLoops Random DFS', 'numbat':'LedgerLoops Numbat', 'cycles':'Cycles public notebook (local)'}
ORDER = ('random','numbat','cycles')


def positions(graph):
    value = Counter()
    for (a,b), amount in graph.items():
        value[a] -= amount
        value[b] += amount
    return {node:n for node,n in value.items() if n}


def main():
    workloads = json.loads(WORKLOAD.read_text())
    ledger = json.loads((OUT/'ledgerloops-results.json').read_text())
    cycles = json.loads((OUT/'cycles-results.json').read_text())
    expected_hash = hashlib.sha256(WORKLOAD.read_bytes()).hexdigest()
    assert ledger['complete'] and len(ledger['runs']) == ledger['expected_runs'] == 54
    assert ledger['input_sha256'] == cycles['workload_sha256'] == expected_hash
    assert len(cycles['cases']) == 9 and sum(len(c['runs']) for c in cycles['cases']) == 27
    cases = {c['name']:c for c in workloads['cases']}
    by_case = defaultdict(list)
    for run in ledger['runs']:
        case = cases[run['case']]
        graph = {(e['source'],e['target']):e['amount'] for e in case['edges']}
        remaining = {(e['source'],e['target']):e['amount'] for e in run['remaining_edges']}
        assert set(remaining) <= set(graph)
        assert all(type(v) is int and 0 < v <= graph[e] for e,v in remaining.items())
        assert positions(graph) == positions(remaining)
        replay = dict(graph)
        for cycle in run['cycles']:
            nodes, amount = cycle['nodes'], cycle['amount']
            assert len(nodes) >= 3 and len(set(nodes)) == len(nodes) and type(amount) is int and amount > 0
            for i,a in enumerate(nodes):
                edge = (a,nodes[(i+1)%len(nodes)])
                assert replay.get(edge,0) >= amount
                replay[edge] -= amount
        assert {e:v for e,v in replay.items() if v} == remaining
        assert sum(graph.values()) - sum(remaining.values()) == run['amount_cleared']
        comm = run['communication']
        assert comm['data_attempts'] == comm['application_deliveries'] == run['protocol_metrics']['messages']
        assert sum(comm['serialized_json_bytes_by_kind'].values()) == comm['serialized_json_bytes']
        assert run['source_sha256'] == ledger['source_sha256']
        by_case[run['method'],run['case']].append(run)
    for (method,name), runs in by_case.items():
        assert len(runs) == 3 and len({r['determinism_sha256'] for r in runs}) == 1
    for case in cycles['cases']:
        graph = {(e['source'],e['target']):e['amount'] for e in cases[case['name']]['edges']}
        for run in case['runs']:
            remaining = {(e['source'],e['target']):e['amount'] for e in run['remaining_edges']}
            cleared = {(e['source'],e['target']):e['amount'] for e in run['cleared_edges']}
            assert set(remaining) <= set(graph) and set(cleared) <= set(graph)
            assert all(remaining.get(e,0) + cleared.get(e,0) == v for e,v in graph.items())
            assert positions(remaining) == positions(graph) and not positions(cleared)
            assert sum(cleared.values()) == run['cleared_amount']
            assert all(run['audits'].values())
        by_case['cycles',case['name']] = case['runs']
    for name,digest in ledger['source_sha256'].items():
        assert hashlib.sha256((ROOT/'experiments'/name).read_bytes()).hexdigest() == digest
    upstream = Path('/workspace/cycles-overview')/cycles['source_file']
    assert hashlib.sha256(upstream.read_bytes()).hexdigest() == cycles['source_sha256']
    rows = []
    for family in ('ring32','sparse64','medium256'):
        members = [c for c in workloads['cases'] if c['family'] == family]
        for method in ORDER:
            selected = [by_case[method,c['name']] for c in members]
            init = sum(sum(e['amount'] for e in c['edges']) for c in members)
            cleared = sum(runs[0]['cleared_amount' if method == 'cycles' else 'amount_cleared'] for runs in selected)
            seed_seconds = [statistics.median(r['elapsed_ns']/1e9 if method == 'cycles' else r['runtime_seconds'] for r in runs) for runs in selected]
            seed_percents = [100*runs[0]['cleared_amount' if method == 'cycles' else 'amount_cleared']/sum(e['amount'] for e in c['edges']) for c,runs in zip(members,selected)]
            rows.append(dict(family=family,method=method,label=LABELS[method],nodes_per_graph=len(members[0]['nodes']),
              edges_per_graph=len(members[0]['edges']),graph_seeds=3,timing_repeats=3,
              initial_units_all_graphs=init,cleared_units_all_graphs=cleared,
              cleared_percent=100*cleared/init,seed_percent_min=min(seed_percents),seed_percent_max=max(seed_percents),
              mean_of_seed_median_seconds=statistics.mean(seed_seconds),seed_median_seconds_min=min(seed_seconds),seed_median_seconds_max=max(seed_seconds),
              mean_messages_per_graph=None if method=='cycles' else statistics.mean(runs[0]['communication']['data_attempts'] for runs in selected),
              mean_json_bytes_per_graph=None if method=='cycles' else statistics.mean(runs[0]['communication']['serialized_json_bytes'] for runs in selected),
              mean_global_input_json_bytes=None if method!='cycles' else statistics.mean(runs[0]['input_json_payload_bytes'] for runs in selected),
              mean_global_setoffs_json_bytes=None if method!='cycles' else statistics.mean(runs[0]['setoffs_json_payload_bytes'] for runs in selected)))
    sentence = ('On three synthetic 256-node graphs, our node-local research strategies cleared '
                '32.2–38.7% of debt within a fixed search budget, versus 67.3% for Cycles’ locally run public notebook solver.')
    cpu = next(line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name'))
    report = dict(title='Horsing Around with LedgerLoops — MDG2, 25 October 2026',measured_on='2026-10-20',
        workload_sha256=expected_hash,ledgerloops_commit=workloads['source_commit'],cycles_commit=cycles['commit_sha'],
        versions=dict(python=platform.python_version(),networkx=cycles['networkx'],matplotlib=matplotlib.__version__,cpu=cpu,platform=platform.platform()),
        aggregation='Cleared percentage = summed cleared units / summed initial units over three graph seeds. Runtime = arithmetic mean of the three per-seed medians of three timing repeats. Messages and bytes = mean per graph; timing repeats never count as new graph samples.',
        talk_sentence=sentence,rows=rows,
        scope='LedgerLoops research DFS/Numbat actors in a reliable serialized event simulator with real JSON encoding; Cycles public educational global-graph solver run locally. Neither runtime is a deployed network/product benchmark.',
        checks=dict(independent_ledger_replay=True,all_node_positions_preserved=True,capacities_respected=True,
                    repeat_determinism=True,communication_accounting=True,source_and_input_pins=True,
                    cycles_upstream_wrapper_negative_cycle_optimality_certificate=True),
        runtime_scope=workloads['timing'],limits=workloads['limits'])
    (OUT/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    with (OUT/'comparison.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    # Standalone slide figure: same medium-size graphs, no invented Cycles network bar.
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.spines.top':False,'axes.spines.right':False,
                         'axes.spines.left':False,'axes.spines.bottom':False,'axes.labelcolor':'#34433a','text.color':'#24362c'})
    fig,axs=plt.subplots(1,3,figsize=(17,7.8),gridspec_kw={'width_ratios':[1.05,1,1.2]})
    fig.patch.set_facecolor('#fafaf5')
    colors=['#819789','#385c47','#b99b79']
    selected=[r for r in rows if r['family']=='medium256']; ypos=np.arange(3)
    for ax in axs:
        ax.set_facecolor('#fafaf5');ax.set_ylim(-.65,2.65);ax.invert_yaxis();ax.set_yticks(ypos)
        ax.tick_params(axis='both',length=0,pad=8);ax.grid(axis='x',alpha=.12,zorder=0)
    axs[0].set_yticklabels(['Random DFS','Numbat','Cycles notebook\n(local core)'])
    for ax in axs[1:]:ax.set_yticklabels([])
    v=[r['cleared_percent'] for r in selected]
    axs[0].barh(ypos,v,color=colors,height=.48,zorder=3)
    axs[0].set_xlim(0,85);axs[0].set_title('Debt cleared',loc='left',weight='bold',pad=18);axs[0].set_xlabel('% of initial debt')
    for y,value in zip(ypos,v):axs[0].text(value+1.6,y,f'{value:.1f}%',va='center',weight='bold')
    v=[r['mean_of_seed_median_seconds'] for r in selected]
    axs[1].barh(ypos,v,color=colors,height=.48,zorder=3)
    axs[1].set_xlim(0,2.05);axs[1].set_title('Local compute time',loc='left',weight='bold',pad=18);axs[1].set_xlabel('Seconds per graph')
    for y,value in zip(ypos,v):axs[1].text(value+.04,y,f'{value:.3f} s',va='center',weight='bold')
    v=[r['mean_json_bytes_per_graph']/1048576 for r in selected[:2]]
    axs[2].barh(ypos[:2],v,color=colors[:2],height=.48,zorder=3)
    axs[2].set_xlim(0,33.5);axs[2].set_title('Logical communication',loc='left',weight='bold',pad=18);axs[2].set_xlabel('MiB of benchmark JSON per graph')
    for y,value,r in zip(ypos,v,selected):axs[2].text(value+.5,y,f'{value:.1f} MiB\n{r["mean_messages_per_graph"]:,.0f} messages',va='center',fontsize=11,weight='bold')
    axs[2].text(.4,2,'Unmeasured\nNo transport in notebook',va='center',color='#715c48',fontsize=11)
    fig.suptitle('Clearing on identical 256-node synthetic graphs',x=.055,y=.95,ha='left',fontsize=22,weight='bold')
    fig.text(.055,.875,'1,536 obligations per graph · 3 graph seeds · 3 timing repeats · fixed cancellation objective',fontsize=13)
    fig.text(.055,.165,'LedgerLoops: finite 500-tick search window, then drain; 250,000-message admission cap.\nCycles: official public notebook solver with the whole graph; hosted service, proofs and settlement excluded.',fontsize=11,linespacing=1.7)
    fig.text(.055,.055,'Times include construction + algorithm; simulation/scheduler/JSON costs differ from a solver call.\nLogical JSON excludes network headers, ACKs and retries. Cycles protocol communication is unavailable, not zero.',fontsize=10,color='#526256',linespacing=1.6)
    fig.subplots_adjust(left=.13,right=.97,top=.77,bottom=.29,wspace=.29)
    fig.savefig(OUT/'comparison.png',dpi=200,facecolor=fig.get_facecolor())
    fig.savefig(OUT/'comparison.svg',facecolor=fig.get_facecolor())
    plt.close(fig)
    # Printable/self-contained methodology companion, with relative links to supplied artifacts.
    table_rows=''.join('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in [r['family'],r['label'],f"{r['nodes_per_graph']:,}/{r['edges_per_graph']:,}",f"{r['cleared_units_all_graphs']:,} / {r['initial_units_all_graphs']:,}",f"{r['cleared_percent']:.2f}%",f"{r['mean_of_seed_median_seconds']:.4f}", 'Unmeasured' if r['mean_messages_per_graph'] is None else f"{r['mean_messages_per_graph']:,.0f}", 'Unmeasured' if r['mean_json_bytes_per_graph'] is None else f"{r['mean_json_bytes_per_graph']/1048576:.2f}"] )+'</tr>' for r in rows)
    text=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>MDG2 LedgerLoops comparison</title>
<style>body{{font:17px/1.5 system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#24362c}}img{{max-width:100%}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;border-bottom:1px solid #ccc;padding:8px}}blockquote{{font-size:23px;border-left:4px solid #385c47;padding-left:20px}}code{{overflow-wrap:anywhere}}a{{color:#385c47}}</style>
<h1>Horsing Around with LedgerLoops</h1><p>MDG2 · 25 October 2026 · Measurements: 20 October 2026</p>
<h2>One defensible talk sentence</h2><blockquote>{html.escape(sentence)}</blockquote>
<h2>Comfort-zone UI</h2><img src="comfort-zone-ui.png" alt="Actual comfort-zone UI with demo data"><p>Actual app, unchanged DOM/CSS, source <code>{workloads['source_commit']}</code>. Isolated fabricated TEST data: Alice owes Bob 3; own comfort −5…15, own grant 20; mirrored peer comfort −8…10, peer grant 8; shared zone −5…10. No credentials visible. This screenshot illustrates preferences, not settlement.</p>
<h2>Comparable-input measurements</h2><img src="comparison.png" alt="Comparison chart"><table><thead><tr><th>Family</th><th>Implementation</th><th>Nodes/edges per graph</th><th>Cleared/initial units, 3 graphs</th><th>Cleared</th><th>Seconds per graph</th><th>Messages per graph</th><th>JSON MiB per graph</th></tr></thead><tbody>{table_rows}</tbody></table>
<p>{html.escape(report['aggregation'])}</p><p>Amount cleared counts each edge reduction once: a three-edge loop cleared by 3 removes 9 units of aggregate obligation. Units are synthetic integer weights, not money or distinct economic value.</p>
<h2>Versions and environment</h2><p>LedgerLoops algorithms: <code>{workloads['source_commit']}</code>; unchanged <code>experiments/distributed.py</code> Random DFS and <code>experiments/numbat.py</code> Numbat (capacity power 4, snapshot capacity enabled, close-first disabled). Cycles: <a href="https://github.com/informalsystems/cycles-overview/blob/{cycles['commit_sha']}/utils/graph_max_flow_solvers.py">official public notebook solver</a>, <code>{cycles['commit_sha']}</code>; NetworkX {cycles['networkx']}, Python {platform.python_version()} on {html.escape(cpu)}, Linux x86-64. Algorithms were run sequentially in the same container, with warm imports and fresh graph/state for each timing repetition. See raw artifacts for every timing and all source hashes.</p>
<h2>Workloads, budget and audits</h2><p>Nine prospectively frozen graphs: 32-node rings (32 arcs), 64 nodes/256 arcs and 256 nodes/1,536 arcs, each using seeds 0, 1 and 2. Every graph starts with a strongly connected directed ring; larger graphs add seeded random arcs. No self loops or antiparallel pairs; each edge amount is uniformly sampled from integers 1…100. All methods receive exactly the same capacities and minimize remaining debt without new credit, preserving each node's signed net position. Cycles uses the upstream default unit-weight min-cost max-flow solver.</p><p>LedgerLoops settings: horizon 500 simulated ticks, delays 1…5 ticks, retry interval 50, max path 100, search budget 256 and a 250,000-message admission cutoff; in-flight work drains afterward. No final run hit the message cutoff. Negative ring results are retained: Random DFS seed 0 cleared nothing within the fixed window, while the Cycles reference cleared 192 units. Search is finite and contention can prevent completion.</p><p>Every completed cycle and final ledger was independently replayed; edge capacities and all node net positions reconcile. Cycles results additionally passed a no-negative-cycle certificate for minimum retained debt. All timing repeats preserved the same ledgers and communication counts. <a href="comparison.json">Audit summary and aggregation</a> · <a href="comparison.csv">CSV</a> · <a href="ledgerloops-results.json">LedgerLoops raw results</a> · <a href="cycles-results.json">Cycles raw results</a>.</p>
<h2>Relevant limitations</h2><ul><li>The Cycles baseline is its public educational notebook core run locally, not a benchmark of the hosted cycles.money product or its current production code, proving, encryption, TEE, chain finality or settlement.</li><li>The LedgerLoops algorithms are route-bearing research simulations: nodes use local balances and received messages, but tokens reveal paths/visited identities. They are not the photographed app's distinct neighbour-private hashlock protocol, and this is not a privacy proof.</li><li>LedgerLoops runtime includes protocol serialization, reservations and scheduler overhead; Cycles runtime includes graph construction and its global solver. These are actual local implementation costs, not equal-role production latencies.</li><li>LedgerLoops communication measures exact compact JSON envelopes encoded, queued and decoded by the adapter. The reliable model has no ACK/retransmission implementation; TCP/TLS/HTTP, deployment, replicated bilateral storage, user approvals, faults and input distribution are excluded.</li><li>Cycles has no protocol transport to instrument here, so its messages/wire bytes are unmeasured. Its mean input and output payloads on the 256-node graphs are {next(r for r in rows if r['family']=='medium256' and r['method']=='cycles')['mean_global_input_json_bytes']/1024:.1f} KiB and {next(r for r in rows if r['family']=='medium256' and r['method']=='cycles')['mean_global_setoffs_json_bytes']/1024:.1f} KiB; these are serialization sizes, not measured network traffic.</li><li>Only three synthetic graph seeds, static capacities and three timing repeats per seed: no real-business workload, arrivals, losses, crashes, hostile peers or statistically representative performance claim.</li><li>Comfort clearing can increase gross debt while lowering discomfort. The pictured comfort settings and the cancellation-only benchmark evaluate different functions.</li></ul>
<p>Additional sources: <a href="https://cycles.money/blog/an-introduction-to-mtcs">official MTCS explanation</a>; <a href="https://github.com/informalsystems/cycles-overview/blob/{cycles['commit_sha']}/concepts.md#settlement">Cycles architecture</a>; <a href="comfort-zone-ui-provenance.json">screenshot provenance</a>; <a href="cycles-provenance.json">Cycles source provenance</a>.</p></html>'''
    (OUT/'report.html').write_text(text)
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
