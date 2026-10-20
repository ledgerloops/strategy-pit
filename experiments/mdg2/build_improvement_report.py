"""Render all preregistered outcomes, including negative results."""
from collections import defaultdict
import csv
import hashlib
import html
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'artifacts/mdg2-improvement-2026-10-20'
LABELS = {'numbat':'Numbat baseline', 'close_first':'Existing close-first control',
          'objective_closure':'Objective-scored closure', 'cycles':'Cycles public solver'}
METHODS = list(LABELS)


def main():
    data = json.loads((OUT/'results.json').read_text())
    assert data['complete'] and len(data['runs']) == data['expected_runs'] == 216
    workload_path = ROOT/'experiments/mdg2/improvement-workloads.json'
    assert hashlib.sha256(workload_path.read_bytes()).hexdigest() == data['input_sha256']
    cases = json.loads(workload_path.read_text())['cases']
    grouped = defaultdict(list)
    for run in data['runs']:
        grouped[run['method'], run['case']].append(run)
    oracle = {c['name']:c for c in data['oracle_cases']}
    assert len(oracle) == len(cases) == 24
    for runs in grouped.values():
        assert len(runs) == 3 and len({r['determinism_sha256'] for r in runs}) == 1
    rows = []
    for split in ('development', 'heldout'):
        for family in ('ring32', 'sparse64', 'medium256', 'pooled'):
            members = [c for c in cases if c['split'] == split and (family == 'pooled' or c['family'] == family)]
            initial = sum(sum(e['amount'] for e in c['edges']) for c in members)
            maximum = sum(oracle[c['name']]['cleared_amount'] for c in members)
            for method in METHODS:
                selected = [oracle[c['name']]['runs'] if method == 'cycles' else grouped[method,c['name']]
                            for c in members]
                cleared = sum(r[0]['cleared_amount' if method == 'cycles' else 'amount_cleared'] for r in selected)
                medians = [statistics.median(r['elapsed_ns']/1e9 if method == 'cycles' else r['runtime_seconds']
                                            for r in runs) for runs in selected]
                messages = None if method == 'cycles' else sum(r[0]['communication']['data_attempts'] for r in selected)
                byte_count = None if method == 'cycles' else sum(r[0]['communication']['serialized_json_bytes'] for r in selected)
                rows.append(dict(split=split, family=family, method=method, graphs=len(members),
                    initial_debt=initial, maximum_nettable=maximum, amount_cleared=cleared,
                    percent_initial=100*cleared/initial, percent_maximum=100*cleared/maximum,
                    sum_graph_median_seconds=sum(medians), mean_graph_median_seconds=statistics.mean(medians),
                    messages=messages, json_bytes=byte_count,
                    mean_messages=None if messages is None else messages/len(members),
                    mean_json_mib=None if byte_count is None else byte_count/len(members)/1048576))
    gates = []
    for split in ('development', 'heldout'):
        base = next(r for r in rows if (r['split'],r['family'],r['method']) == (split,'pooled','numbat'))
        for method in METHODS[1:3]:
            alt = next(r for r in rows if (r['split'],r['family'],r['method']) == (split,'pooled',method))
            ratios = {key:alt[key]/base[key] for key in ('amount_cleared','messages','json_bytes','sum_graph_median_seconds')}
            family_ratios = {}
            family_guard = True
            for family in ('ring32','sparse64','medium256'):
                alternative = next(r['amount_cleared'] for r in rows if
                    (r['split'],r['family'],r['method']) == (split,family,method))
                baseline = next(r['amount_cleared'] for r in rows if
                    (r['split'],r['family'],r['method']) == (split,family,'numbat'))
                family_ratios[family] = alternative/baseline if baseline else None
                family_guard = family_guard and alternative >= .95*baseline
            passes = (ratios['amount_cleared'] >= 1.05 and all(ratios[k] <= 1.25 for k in
                ('messages','json_bytes','sum_graph_median_seconds')) and family_guard)
            gates.append(dict(split=split, method=method, ratios_to_baseline=ratios,
                              family_clearing_ratios=family_ratios, passes=passes))
    report = dict(rows=rows, gates=gates, source_sha256=data['source_sha256'],
        plan_sha256=data['plan_sha256'], input_sha256=data['input_sha256'],
        python=data['python'], networkx=data['networkx'], upstream_commit=data['upstream_commit'],
        limits=data['plan']['limits'],
        aggregation='Clearing and traffic summed once per graph; runtime is the mean of per-graph medians of 3 repeats. Development 2 seeds/family; heldout 6 seeds/family. Pooled ratios weight larger graphs more.',
        terminology='Clearing potential is the maximum sum of original-edge debt reductions achievable without adding money or credit, while preserving every net position. Net internal debt (sum of positive net positions) is preserved by cancellation. Endogenous debt is not a verified Cycles synonym for the cancellable portion.')
    (OUT/'comparison.json').write_text(json.dumps(report, indent=2)+'\n')
    with (OUT/'comparison.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    colors = ['#8c9690','#73a593','#216c56','#c18b3b']
    fig, axes = plt.subplots(1, 3, figsize=(15.5,5.4), gridspec_kw={'width_ratios':[1.2,1,1]})
    fig.patch.set_facecolor('#faf9f5')
    families = ['ring32','sparse64','medium256']
    for index,method in enumerate(METHODS):
        points = [next(r for r in rows if (r['split'],r['family'],r['method']) == ('heldout',f,method)) for f in families]
        axes[0].bar([i+(index-1.5)*.2 for i in range(3)], [r['percent_maximum'] for r in points],
                    width=.19, color=colors[index], label=LABELS[method])
    axes[0].set_xticks(range(3), ['32 / 32','64 / 256','256 / 1,536'])
    axes[0].set_xlabel('Nodes / directed obligations per graph')
    axes[0].set_ylabel('Clearing potential achieved (%)')
    axes[0].set_ylim(0,110)
    axes[0].set_title('Clearing on held-out graphs')
    medium = [next(r for r in rows if (r['split'],r['family'],r['method']) == ('heldout','medium256',m)) for m in METHODS]
    axes[1].bar(range(4),[r['mean_graph_median_seconds'] for r in medium],color=colors)
    axes[1].set_xticks(range(4),['Baseline','Close first','Scored','Cycles'],rotation=20)
    axes[1].set_title('256-node runtime')
    axes[1].set_ylabel('Seconds per graph')
    axes[2].bar(range(3),[r['mean_json_mib'] for r in medium[:3]],color=colors[:3])
    axes[2].set_xticks(range(3),['Baseline','Close first','Scored'],rotation=20)
    axes[2].set_title('256-node communication')
    axes[2].set_ylabel('Compact JSON MiB per graph')
    for ax in axes:
        ax.set_facecolor('#faf9f5')
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle('LedgerLoops: testing earlier cycle closure',fontsize=20,x=.05,ha='left')
    fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,.055))
    fig.text(.05,.018,'6 held-out seeds per size · 3 timing repeats · same fixed search budget · static simulation · Cycles transport: unmeasured',fontsize=10)
    fig.subplots_adjust(left=.06,right=.98,top=.83,bottom=.27,wspace=.35)
    fig.savefig(OUT/'comparison.png',dpi=200)
    fig.savefig(OUT/'comparison.svg')
    table = ''.join('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in [
        r['split'],r['family'],LABELS[r['method']],r['amount_cleared'],f"{r['percent_initial']:.2f}%",
        f"{r['percent_maximum']:.2f}%",f"{r['mean_graph_median_seconds']:.4f}",
        'N/A' if r['mean_messages'] is None else f"{r['mean_messages']:,.0f}",
        'N/A' if r['mean_json_mib'] is None else f"{r['mean_json_mib']:.2f}"])+'</tr>' for r in rows if r['family'] != 'pooled')
    gate_text = ''.join('<li>'+html.escape(f"{g['split']} {LABELS[g['method']]}: {'PASS' if g['passes'] else 'FAIL'}; "
        f"clearing {(g['ratios_to_baseline']['amount_cleared']-1)*100:+.2f}%, "
        f"messages {(g['ratios_to_baseline']['messages']-1)*100:+.2f}%, "
        f"JSON bytes {(g['ratios_to_baseline']['json_bytes']-1)*100:+.2f}%, "
        f"runtime {(g['ratios_to_baseline']['sum_graph_median_seconds']-1)*100:+.2f}%.")+'</li>' for g in gates)
    limits = ''.join(f'<li>{html.escape(s)}</li>' for s in report['limits'])
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>LedgerLoops closure experiment</title>
<style>body{{font:16px/1.5 system-ui;max-width:1200px;margin:40px auto;padding:0 20px;color:#243a30}}img{{width:100%}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{text-align:left;padding:7px;border-bottom:1px solid #ddd}}code{{overflow-wrap:anywhere}}</style>
<h1>Earlier cycle closure: a fixed-policy experiment</h1><p>20 October 2026. Research simulation; no app or demo credentials changed.</p>
<p>The candidate closes the best currently visible cycle by estimated aggregate debt reduction. The control enables the existing close-first switch. Both retain local capacity/reservation checks and unchanged settlement.</p>
<img src="comparison.png" alt="Held-out clearing, runtime and communication">
<h2>Prospective promotion rule</h2><p>At least 5% more pooled held-out clearing; at most 25% more messages, JSON bytes and runtime; no family loses more than 5% of baseline clearing; all audits pass. Every fixed method was tested regardless of development scores; no tuning. Seven independent correctness tests pass.</p><ul>{gate_text}</ul>
<h2>Every family and split</h2><p>{html.escape(report['aggregation'])}</p><table><tr><th>Split</th><th>Family</th><th>Method</th><th>Cleared units</th><th>% initial debt</th><th>Clearing potential achieved (%)</th><th>Seconds/graph</th><th>Messages/graph</th><th>JSON MiB/graph</th></tr>{table}</table>
<h2>What “100%” means</h2><p>{html.escape(report['terminology'])} Cycles' public solver reaches the certified maximum for these graphs. This is not 100% of all debt or of NID. See <a href="https://cycles.money/blog/an-introduction-to-mtcs">Cycles' cyclic structure explanation</a>.</p>
<p>Independent validation: 216 local timing runs checked, 72 unique method/graph ledgers replayed, and 24 oracle optima certified by a separately written Bellman–Ford audit. See <a href="independent-audit.json">independent audit results</a>. Close-first improves 11 of 18 held-out graphs, ties 6 and loses 1; objective scoring improves 13, ties 3 and loses 2. Family promotion guards are aggregate, not per-graph guarantees.</p>
<h2>Versions and model</h2><p>LedgerLoops base 1e0e87d4859e470d87b430b488c64db3c08df6ae plus candidate SHA256 <code>{data['plan']['candidate_sha256']}</code>. Cycles public notebook <code>{data['upstream_commit']}</code>; Python {data['python']}; NetworkX {data['networkx']}. Source, input and plan hashes are in <a href="comparison.json">comparison.json</a>.</p>
<p>Same 500-tick horizon, 250,000-message soft admission cutoff plus drain, maximum path 100, search budget 256, delays 1–5, retry 50. Runtime includes fresh engine/graph construction and clearing, excludes parsing and audits. No Internet latency measurement. All original edge bounds and node net positions were audited; every Cycles output has a negative-cycle optimality certificate.</p>
<ul>{limits}</ul><p><a href="comparison.csv">CSV</a> · <a href="results.json">Raw results</a> · <a href="REPRODUCE.txt">Reproduce</a></p></html>'''
    (OUT/'report.html').write_text(page)
    print(json.dumps({'gates':gates,'heldout_medium':[r for r in rows if r['split']=='heldout' and r['family']=='medium256']},indent=2))


if __name__ == '__main__':
    main()
