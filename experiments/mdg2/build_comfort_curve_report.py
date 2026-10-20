"""Render the fixed comfort/headroom message curves without rerunning them."""
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
OUT = ROOT/'artifacts/mdg2-comfort-curves-2026-10-20'
LABELS = {'cancellation':'Cancellation only','comfort_headroom':'Comfort-assisted headroom'}
COLORS = {'cancellation':'#858e89','comfort_headroom':'#18705b'}


def main():
    data = json.loads((OUT/'results.json').read_text())
    assert data['complete'] and len(data['runs']) == data['expected_runs'] == 240
    followup = None
    if (OUT/'decrease-first-results.json').exists():
        candidate = json.loads((OUT/'decrease-first-results.json').read_text())
        if candidate.get('complete'):
            followup = candidate
            extension = [dict(r,policy='decrease_first') for r in candidate['runs']
                         if r['phase']=='extension' and r['method']=='decrease_first']
            assert len(extension)==120
            data['runs'] += extension
            LABELS['decrease_first']='Headroom · debt-first routing'
            COLORS['decrease_first']='#2f6fa0'
    groups = defaultdict(list)
    for run in data['runs']:
        groups[run['family'],run['profile'],run['mode'],run['policy'],run['budget_per_trustline']].append(run)
    rows = []
    for key,runs in sorted(groups.items()):
        assert len(runs) == 3
        family,profile,mode,policy,budget = key
        potential = sum(r['clearing_potential'] for r in runs)
        savings = sum(r['snapshot_savings'] for r in runs)
        rows.append(dict(family=family,profile=profile,mode=mode,policy=policy,budget_per_trustline=budget,
            graph_seeds=3,nodes=runs[0]['nodes'],trustlines=runs[0]['trustlines'],
            mean_actual_messages_per_trustline=statistics.mean(r['actual_messages_per_trustline'] for r in runs),
            reference_gross=sum(r['reference_gross'] for r in runs),
            oracle_minimum_gross=sum(r['oracle_minimum_gross'] for r in runs),
            clearing_potential=potential,snapshot_savings=savings,
            clearing_potential_achieved_percent=100*savings/potential if potential else None,
            final_gross=sum(r['final']['gross_debt'] for r in runs),
            final_discomfort=sum(r['final']['discomfort'] for r in runs),
            assisted_moves=sum(r['final']['assisted_moves'] for r in runs),
            mean_json_mib=statistics.mean(r['final']['message_bytes']/1048576 for r in runs),
            mean_runtime_seconds=statistics.mean(r['runtime_seconds'] for r in runs),
            offered=sum(r['offered'] for r in runs),accepted=sum(r['accepted'] for r in runs),
            blocked=sum(r['blocked'] for r in runs),blocked_value=sum(r['blocked_value'] for r in runs)))
    report = dict(rows=rows,plan=data['plan'],freeze=data['freeze'],python=data['python'],networkx=data['networkx'],
                  graph_label='Clearing potential achieved (%)',
                  x_label='Application messages sent per original trustline',
                  interpretation='Static and final temporal snapshots; temporal savings are relative to replaying exactly the same accepted stream without clearing. Budget points and comfort profiles reuse graph/stream seeds, not independent replications.',
                  warning='Broad zones admit the hard-limit oracle. Narrow zones may prevent achieving that relaxed ceiling. This differs from the original cancellation-only Cycles comparison; original-edge debt capacities are not the headroom limits here.')
    if followup is not None:
        report['followup_metadata']={k:v for k,v in followup.items() if k not in ('runs','oracles','workloads','cases')}
    (OUT/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    with (OUT/'comparison.csv').open('w') as handle:
        writer = csv.DictWriter(handle,fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    for family in ('small16','medium32'):
        sample = next(r for r in rows if r['family'] == family)
        fig,axes = plt.subplots(2,2,figsize=(13,8.8),sharex=True,sharey=True)
        fig.patch.set_facecolor('#faf9f5')
        values = []
        for row_index,profile in enumerate(('broad','narrow')):
            for col_index,mode in enumerate(('static','arrivals')):
                ax = axes[row_index,col_index]
                ax.set_facecolor('#faf9f5')
                for policy in LABELS:
                    selected = sorted((r for r in rows if (r['family'],r['profile'],r['mode'],r['policy']) ==
                                      (family,profile,mode,policy)),key=lambda r:r['budget_per_trustline'])
                    for seed in data['plan']['seeds']:
                        seed_runs = sorted((r for r in data['runs'] if (r['family'],r['profile'],r['mode'],r['policy'],r['seed']) ==
                                            (family,profile,mode,policy,seed)),key=lambda r:r['budget_per_trustline'])
                        defined = [r for r in seed_runs if r['clearing_potential_achieved_percent'] is not None]
                        ax.plot([r['actual_messages_per_trustline'] for r in defined],
                                [r['clearing_potential_achieved_percent'] for r in defined],
                                color=COLORS[policy],alpha=.23,lw=1)
                    defined = [r for r in selected if r['clearing_potential_achieved_percent'] is not None]
                    ax.plot([r['mean_actual_messages_per_trustline'] for r in defined],
                            [r['clearing_potential_achieved_percent'] for r in defined],
                            color=COLORS[policy],marker='o',lw=2.4,label=LABELS[policy])
                    values += [r['clearing_potential_achieved_percent'] for r in defined]
                ax.axhline(100,color='#b58a42',ls='--',lw=1)
                ax.set_xscale('symlog',linthresh=1)
                ax.set_xticks([1,4,16,64,256,1024],['1','4','16','64','256','1,024'])
                ax.grid(alpha=.17)
                ax.spines[['top','right']].set_visible(False)
                ax.set_title(('Broad comfort zones' if profile=='broad' else 'Narrow comfort zones')+
                             (' · static ledger' if mode=='static' else ' · random arrivals'),fontsize=12)
                if col_index==0:
                    ax.set_ylabel('Clearing potential achieved (%)')
                if row_index==1:
                    ax.set_xlabel('Messages sent per original trustline')
        axes[0,0].set_ylim(min(-3,min(values)-3),105)
        fig.suptitle('Clearing potential versus communication',x=.07,ha='left',fontsize=21,y=.98)
        fig.text(.07,.925,f'{sample["nodes"]} nodes · {sample["trustlines"]} original trustlines · 3 fixed seeds · local decisions, serial research protocol',fontsize=12)
        fig.legend(*axes[0,0].get_legend_handles_labels(),loc='lower center',ncol=len(LABELS),frameon=False,bbox_to_anchor=(.5,.065))
        fig.text(.07,.047,'Bold curves: pooled savings / pooled potential. Faint curves: individual graph/stream seeds.',fontsize=10)
        fig.text(.07,.025,'Potential uses fixed credit limits; narrow comfort zones can restrict it. Messages include search and settlement.',fontsize=10)
        fig.subplots_adjust(left=.08,right=.98,top=.865,bottom=.18,hspace=.25,wspace=.15)
        fig.savefig(OUT/f'clearing-potential-{family}.png',dpi=200)
        fig.savefig(OUT/f'clearing-potential-{family}.svg')
        plt.close(fig)
    highest = [r for r in rows if r['budget_per_trustline']==max(data['plan']['message_budgets_per_original_trustline'])]
    def format_value(value):
        return 'Undefined' if value is None else f'{value:.2f}'
    table = ''.join('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in
        [r['family'],r['profile'],r['mode'],LABELS[r['policy']],
         format_value(r['mean_actual_messages_per_trustline']),format_value(r['clearing_potential_achieved_percent']),
         r['final_gross'],r['final_discomfort'],r['assisted_moves'],f'{r["accepted"]}/{r["offered"]}'])+'</tr>' for r in highest)
    validation = ''
    if followup is not None:
        gate = followup['gate']
        validation_rows = []
        for profile in ('broad','narrow'):
            for mode in ('static','arrivals'):
                cells = []
                for method in ('comfort_headroom','decrease_first'):
                    selected = [r for r in followup['runs'] if
                                (r['phase'],r['profile'],r['mode'],r['method'],r['budget_per_trustline']) ==
                                ('heldout',profile,mode,method,1024)]
                    assert len(selected)==3
                    cells.append(100*sum(r['snapshot_savings'] for r in selected)/
                                 sum(r['clearing_potential'] for r in selected))
                validation_rows.append(f'<tr><td>{profile}</td><td>{mode}</td>'+
                                       ''.join(f'<td>{value:.2f}%</td>' for value in cells)+'</tr>')
        validation = f'''<h2>Fresh-seed routing validation</h2>
<p>The separate debt-first variant shuffles candidates as before, then prioritizes neighbours whose local balance would decrease. Helper edges remain eligible. Its 120 extension runs appear in the curves above; those original seeds are descriptive, not fresh validation.</p>
<p>A prospectively frozen check used 32 nodes, 96 trustlines, fresh seeds 401–403, both comfort profiles, both arrival modes, and budgets 256 and 1,024. The high-budget gate <strong>{'passed' if gate['passed'] else 'failed'}</strong>: pooled snapshot savings changed by {100*gate['pooled_gain_fraction']:+.2f}% against a required gain of at least 5%. Actual message, JSON-byte and runtime ratios were {gate['costs']['messages']['ratio']:.3f}, {gate['costs']['json_bytes']['ratio']:.3f} and {gate['costs']['runtime_seconds']['ratio']:.3f}; each ceiling was 1.25. Every profile/mode cell also had to avoid a savings regression greater than 5%. Runtime has only one sample per run.</p>
<table><tr><th>Comfort</th><th>Mode</th><th>Original headroom: potential achieved</th><th>Debt-first: potential achieved</th></tr>{''.join(validation_rows)}</table>
<p>{'This supports the candidate only on these tested serial research workloads.' if gate['passed'] else 'The candidate is retained as a measured tradeoff and is not promoted over the original headroom policy.'} See <a href="decrease-first-results.json">all follow-up results and the full gate</a> and <a href="decrease-first-independent-audit.json">independent follow-up audit</a>.</p>'''
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Comfort headroom: clearing potential and messages</title>
<style>body{{font:16px/1.5 system-ui;color:#233d31;max-width:1150px;margin:40px auto;padding:0 24px}}img{{width:100%}}table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{padding:7px;border-bottom:1px solid #ccc;text-align:left}}code{{overflow-wrap:anywhere}}a{{color:#17654e}}</style>
<h1>Comfort zones as clearing headroom</h1><p>20 October 2026 · Fixed synthetic experiment · {len(data['runs'])} curve runs{'; 48 additional fresh-seed validation runs' if followup else ''}</p>
<p>Each participant checks its own balances and bilateral preferences. A helper may increase exposure only when the actual app comfort rule permits it. Every settled cycle reduces total absolute debt, preserves every node's net position, and makes no relationship less comfortable. The cancellation control allows only debt decreases.</p>
<h2>Communication budget curves</h2><img src="clearing-potential-medium32.png" alt="Clearing potential achieved against messages per original trustline for32nodes">
<img src="clearing-potential-small16.png" alt="Same comparison for16nodes">
<p>Each line uses five prospectively fixed message allowances: 4, 16, 64, 256 and 1,024 per original undirected trustline. Horizontal positions are actual messages sent, not allowance. Zero-balance helper links count as trustlines. Thick curves pool savings and potential across three seeds; thin curves retain individual outcomes. No smoothing or clipping of negative savings.</p>
<h2>Random transactions over time</h2><p>Poisson arrivals at rate 1 per time unit through time 40, uniformly sampled original trustlines, signed amounts ±1, ±2 or ±3. The same graph and offered stream are reused for every policy and budget. Clearing service credits accrue linearly with simulated time; unused credits carry forward. Each service slot fully completes before its next external transaction. There is one final bounded service slot at time 40 and no unbudgeted clearing afterward.</p>
<p>All hard grants are 10,000 units. Initial gross debt plus absolute offered volume is below that bound, so all methods and the no-clearing reference accept every offered transaction. Blocked count and value are still recorded and asserted to be zero. This isolates clearing effectiveness from admission differences.</p>
<h2>Definition of clearing potential</h2><p>Replay the accepted transaction stream on the initial signed ledger without clearing to obtain reference gross debt D. An offline min-cost flow computes minimum gross debt D* under the same hard grants and final node net positions. Clearing potential is D−D*. The plotted fraction is (D−actual final debt)/(D−D*). This measures final-snapshot savings; cumulative historical cycle reductions are a separate quantity because arriving transactions can net differently after prior clearing.</p>
<p>Broad zones coincide with the credit limits. Narrow zones use independently sampled endpoint half-widths 1, 3 or 6, with their shared intersection and bilateral assistance opt-in. For narrow zones the plotted denominator is a relaxed hard-limit ceiling, not the exact preference-constrained reachable optimum. Both balance directions and explicitly consented zero-balance helper channels are available; this differs from the original cancellation-only Cycles benchmark's original-edge capacity model.</p>
<p>With fixed feasible bounds, min-cost flow optimality is characterized by the absence of improving residual cycles. Those cycles can require undoing earlier choices or increasing helper balances, which is why more cancellation-only searches need not attain the optimum. See <a href="https://courses.csail.mit.edu/6.854/17/Scribe/s11-minCostFlow.html">MIT's cycle-cancellation notes</a>. This finite randomized search does not itself provide an optimality certificate; the independent offline reference does.</p>
<p>Theoretical inference for the original uniformly shuffled policy: on a static integer ledger with broad zones equal to hard bounds, bilateral helper consent, fair repeated initiation, ideal full-support random choices and enough quota to explore and settle any simple cycle, each improving residual cycle has a positive chance of discovery. Gross debt strictly decreases in integer steps, giving almost-sure eventual optimality. This supplies no deterministic finite-message guarantee, useful convergence rate or distributed termination certificate. It does not automatically extend to debt-first ordering, narrow path-dependent comfort constraints, ongoing arrivals, or a finite seeded PRNG run.</p>
<h2>Highest-budget outcomes</h2><table><tr><th>Graph</th><th>Comfort</th><th>Mode</th><th>Policy</th><th>Actual messages/line</th><th>Potential achieved%</th><th>Final debt</th><th>Discomfort</th><th>Helper cycles</th><th>Accepted/offered</th></tr>{table}</table>
<p>Debt, discomfort, helper cycles and accepted/offered counts are totals across three seeds; messages/line is the mean. Static rows have no external offers.</p>
{validation}
<h2>Verification and limitations</h2><p>Ten new focused tests and 16 existing comfort tests pass; the routing variant adds six focused tests and seven runner checks. The separate auditor replays all transactions and cycle changes, checks hard limits and comfort consent, and certifies the offline optima using residual-cycle conditions. See <a href="independent-audit.json">independent audit</a>.</p>
<p>This is a reliable, serialized research simulator with path-bearing tokens, staged prepare/commit/cleanup, and no message loss, crash recovery or concurrent arrivals during settlement. A simulator chooses initiators; local actors make routing and acceptance decisions. It is not the app's neighbour-private hashlock protocol. The actual app's bilateral edge-comfort admission rule is reused, but discovery is a new research policy: it may start with a debt reduction that is comfort-neutral, whereas the app's discovery has stricter origin-comfort improvement checks. No app code, tokens or demo data changed.</p>
<p>Communication counts actual compact JSON application messages for discovery and settlement. Initial ledger/preference distribution, external transaction admission transport, network headers and acknowledgements absent from this model are excluded. The auditor checks aggregate and per-kind count/byte consistency against the frozen encoder; complete payload wire logs were not retained for independent re-encoding. Runtime is a single illustrative sample per run; it is not the plotted endpoint or a production latency measurement.</p>
<p>Python {data['python']}; NetworkX {data['networkx']}. All implementation, plan and workload hashes are in <a href="comparison.json">comparison.json</a>. The reference uses NetworkX's network simplex solver, not a measurement of the Cycles hosted service.</p>
<p><a href="comparison.csv">CSV</a> · <a href="results.json">Raw results and ordered receipts</a> · <a href="REPRODUCE.txt">Reproduce</a></p></html>'''
    (OUT/'report.html').write_text(page)
    print(json.dumps(highest,indent=2))


if __name__=='__main__':
    main()
