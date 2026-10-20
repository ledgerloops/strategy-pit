"""Render retained private-hashlock traces; never supplies actor decisions."""
import csv
import gzip
import hashlib
import html
import json
from pathlib import Path
import statistics
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/mdg2-private-stream-2026-10-20'
NAMES = dict(randomized_cancellation='Private cancellation',
             private_nonexpansion='Private comfort headroom',
             private_nonexpansion_filtered='Private headroom + local filter',
             faithful_comfort='Original comfort control')
NAVY, CREAM, BLUE, GREEN, MUTED = '#080e3c', '#fffbea', '#9ab8e5', '#61d15a', '#c2c9db'


def read_run(entry):
    with gzip.open(OUT / entry['file'], 'rt') as handle:
        return json.load(handle)


def points(run):
    """All measured debt changes plus terminal point; no smoothing."""
    rows = []
    previous = None
    for event, point in zip(run['events'], run['trace']):
        x = event['messages'] + event['acknowledgements']
        debt = point['debt']
        if debt != previous:
            rows.append((x, debt, event))
            previous = debt
    rows.append((run['messages']+run['acknowledgements'], run['final']['debt'], {}))
    return rows


def style(ax):
    ax.set_facecolor(NAVY)
    ax.tick_params(colors=MUTED, labelsize=12)
    ax.spines[['top', 'right']].set_visible(False)
    for side in ['bottom', 'left']:
        ax.spines[side].set_color('#6b7296')
    ax.grid(axis='y', color=CREAM, alpha=.13)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax.set_xlabel('Cumulative messages sent (requests + acknowledgements)', color=MUTED, labelpad=10)
    ax.set_ylabel('Uncleared gross debt (TEST)', color=MUTED, labelpad=10)


def draw(ax, run, reference=True):
    rows = points(run)
    ax.step([p[0] for p in rows], [p[1] for p in rows], where='post',
            color=GREEN, lw=1.8, label='Measured endpoint debt')
    if reference:
        shadow = run['observer']['trace']
        ax.step([p['message_count'] for p in shadow],
                [p['same_posted_no_clearing_gross'] for p in shadow],
                where='post', color=BLUE, lw=1.7, alpha=.9, linestyle='--',
                label='Same posted transactions, without clearing¹')
    last = next((e for e in run['events'] if e['kind'] == 'offer' and
                 e['offer_id'] == run['offers'][-1]['offer_id']), None)
    if last:
        xlast = last['messages']+last['acknowledgements']
        ax.axvline(xlast, color=MUTED, lw=1, alpha=.6)
        ax.text(xlast, .98, '  Last offer', transform=ax.get_xaxis_transform(),
                color=MUTED, fontsize=10, va='top')
    style(ax)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    return rows


def summary(run):
    observed = run['observer']['final']
    lengths = {}
    for event in run['events']:
        for item in event.get('local_receipts', []):
            lengths.setdefault(item['receipt']['id'], set()).add(item['node'])
    applied = [x['id'] for x in run['observer']['application_order'] if x['kind'] == 'clearing']
    lens = [len(lengths[ident]) for ident in applied]
    final = run['final']
    return dict(method=run['method'], seed=run['seed'],
                offered=len(run['offers']),
                incorporated_transactions=observed['incorporated']['obligation'],
                final_debt=final['debt'],
                reference_debt=observed['same_posted_no_clearing_gross'],
                completed_loops=len(lens),
                median_loop_length=statistics.median(lens) if lens else 0,
                max_loop_length=max(lens, default=0),
                cumulative_loop_debt_reduction=observed['cumulative_clearing_gross_reduction'],
                requests=run['messages'], acknowledgements=run['acknowledgements'],
                total_messages=run['messages']+run['acknowledgements'],
                payload_mib=(run['message_bytes']+run['ack_body_bytes'])/2**20,
                runtime_seconds=run['runtime_seconds'],
                pending_clearing=observed['pending']['clearing'],
                pending_obligations=observed['pending']['obligation'],
                fully_observed_dependency_blocked=observed['fully_observed_dependency_blocked'],
                pending_offers=len(run['pending_offers']),
                reservations=final['reservations'],
                mirror_mismatches=final['mirror_mismatches'],
                unresolved_proposals=final['unresolved_proposals'],
                censored=run['censored'])


def main():
    data = json.loads((OUT / 'results.json').read_text())
    assert data['complete'] and len(data['runs']) == 7
    followup = json.loads((OUT / 'filtered-results.json').read_text())
    assert followup['complete'] and len(followup['runs']) == 3
    audits = json.loads((OUT / 'independent-audit.json').read_text())
    assert audits['independent_audit_passed']
    runs = [read_run(entry) for entry in data['runs']+followup['runs']]
    summaries = [summary(run) for run in runs]
    original = [s for s in summaries if s['method'] == 'private_nonexpansion']
    filtered = [s for s in summaries if s['method'] == 'private_nonexpansion_filtered']
    cancellation = [s for s in summaries if s['method'] == 'randomized_cancellation']
    debt_improvement = 100*(1-sum(s['final_debt'] for s in filtered)/sum(s['final_debt'] for s in original))
    message_improvement = 100*(1-sum(s['total_messages'] for s in filtered)/sum(s['total_messages'] for s in original))
    cancellation_debt_improvement = 100*(1-sum(s['final_debt'] for s in filtered)/sum(s['final_debt'] for s in cancellation))
    cancellation_message_ratio = sum(s['total_messages'] for s in filtered)/sum(s['total_messages'] for s in cancellation)
    residuals = json.loads((OUT / 'residual-diagnostics.json').read_text())
    residual_table = ''.join('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in
        (NAMES[r['method']], r['case'], bool(r.get('positive_debt_cycle')),
         bool(r.get('improving_headroom_cycle'))))+'</tr>' for r in residuals)
    (OUT / 'summary.json').write_text(json.dumps(summaries, indent=2)+'\n')
    with (OUT / 'summary.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    plt.rcParams.update({'font.family': 'Liberation Sans', 'font.size': 13,
                         'pdf.fonttype': 42, 'svg.fonttype': 'none'})
    target = next(r for r in runs if r['method'] == 'private_nonexpansion_filtered' and r['seed'] == 601)
    fig = plt.figure(figsize=(16, 9), facecolor=NAVY)
    fig.text(.055, .95, 'Transactions arrive. Private hashlocks clear.', color=CREAM,
             fontsize=30, weight='bold', va='top')
    fig.text(.055, .88, '32 nodes · 96 trustlines · 1,000 random offers · seed 601 · local-filter followup',
             color=MUTED, fontsize=17)
    ax = fig.add_axes([.075, .28, .86, .53])
    rows = draw(ax, target)
    fig.legend(*ax.get_legend_handles_labels(), loc='center', bbox_to_anchor=(.5, .17),
               ncol=2, frameon=False, labelcolor=CREAM, fontsize=15)
    fig.text(.055, .105, 'Neighbour-private message contents · no network-wide coordinator · actual SHA-256 hashlocks',
             color=GREEN, fontsize=16)
    fig.text(.055, .06, '¹ Offline, quote-consistent reference. Gross debt includes debt that cannot be cleared in loops.',
             color=MUTED, fontsize=12)
    fig.text(.055, .03, 'Finite-window research run with honest peers and reliable delivery; complete clearing is not guaranteed.',
             color=MUTED, fontsize=12)
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(OUT / f'private-debt-vs-messages.{extension}', dpi=160, facecolor=NAVY)
    plt.close(fig)

    # Explicit local economic effects, on a fixed first-2,000-message window.
    fig, ax = plt.subplots(figsize=(14, 7), facecolor=NAVY)
    style(ax)
    ax.step([r[0] for r in rows], [r[1] for r in rows], where='post',
            color=MUTED, lw=1, label='Measured endpoint debt')
    for clearing, colour, label in [(False, BLUE, 'Transaction application (can increase or net debt)'),
                                    (True, GREEN, 'Hashlock application (local part of a loop)')]:
        chosen = [r for r in rows if bool(r[2].get('local_receipts')) == clearing
                  and r[2].get('balance_changes') and r[0] <= 2000]
        ax.scatter([r[0] for r in chosen], [r[1] for r in chosen], color=colour,
                   s=12, label=label, zorder=3)
    ax.set_xlim(0, 2000)
    visible = [r[1] for r in rows if r[0] <= 2000]
    ax.set_ylim(max(0, min(visible)-8), max(visible)+8)
    ax.set_title('How individual transactions and hashlock applications change debt',
                 loc='left', color=CREAM, fontsize=19, pad=20)
    ax.legend(frameon=False, labelcolor=CREAM, fontsize=11, loc='best')
    fig.tight_layout(pad=2)
    fig.savefig(OUT / 'private-debt-event-detail.png', dpi=160, facecolor=NAVY)
    plt.close(fig)

    fig, axes = plt.subplots(3, 3, figsize=(23, 15), facecolor=NAVY)
    for i, seed in enumerate((601, 602, 603)):
        for j, method in enumerate(('randomized_cancellation', 'private_nonexpansion',
                                    'private_nonexpansion_filtered')):
            run = next(r for r in runs if r['seed'] == seed and r['method'] == method)
            draw(axes[i, j], run)
            axes[i, j].set_title(f'{NAMES[method]} · seed {seed}', color=CREAM, loc='left')
    fig.suptitle('All three workloads: cancellation, headroom, and the local-filter followup',
                 color=CREAM, fontsize=22)
    fig.tight_layout(rect=(0, 0, 1, .96), pad=3)
    fig.savefig(OUT / 'private-debt-all-seeds.png', dpi=140, facecolor=NAVY)
    plt.close(fig)

    table = ''.join(
        '<tr>'+''.join(f'<td>{html.escape(str(value))}</td>' for value in (
            NAMES[s['method']], s['seed'], f"{s['incorporated_transactions']}/{s['offered']}",
            s['final_debt'], s['reference_debt'], s['completed_loops'],
            f"{s['total_messages']:,}", f"{s['payload_mib']:.2f}", f"{s['runtime_seconds']:.2f}",
            s['pending_offers'], s['reservations']))+'</tr>' for s in summaries)
    report = f"""<!doctype html><meta charset="utf-8"><title>Private hashlock debt stream</title>
<style>body{{font:17px/1.55 system-ui;max-width:1200px;margin:40px auto;padding:0 20px;color:#182236}}
img{{width:100%;height:auto}}table{{border-collapse:collapse;font-size:14px;width:100%}}td,th{{padding:8px;border-bottom:1px solid #ccd;text-align:left}}code{{overflow-wrap:anywhere}}li{{margin:8px 0}}</style>
<h1>Neighbour-private, coordinator-free hashlock debt stream</h1>
<p>These actors use only their own balances, reservations and direct-neighbour messages.
Any node can initiate a search. A loop initiator holds and releases its hashlock secret;
there is no network-wide coordinator, membership list, route or hop count in participant messages.
The simulator has a global delivery queue and a separate observer; neither chooses the winning loop or feeds a global score to nodes.</p>
<img src="private-debt-vs-messages.png" alt="Measured debt and same-posted no-clearing reference against messages sent">
<h2>All retained runs</h2>
<p>Across the three paired development workloads, early local filtering left
<strong>{debt_improvement:.1f}% less gross debt with {message_improvement:.1f}% fewer messages</strong>
than the original private headroom candidate. This is an aggregate comparison on reused development seeds,
not a held-out performance guarantee.</p>
<p>Against cancellation, the filtered headroom method left {cancellation_debt_improvement:.1f}% less debt,
but sent {cancellation_message_ratio:.2f} times as many messages. It trades communication for additional clearing.</p>
<table><tr><th>Method</th><th>Seed</th><th>Posted / offered</th><th>Final debt</th><th>Reference debt</th><th>Complete loops</th><th>Messages</th><th>Payload MiB</th><th>Seconds</th><th>Offer backlog</th><th>Reservations</th></tr>{table}</table>
<p>Messages include actual peer request attempts plus ACK emissions, including preference setup, discovery,
settlement and obligation traffic. Exact serialized JSON body bytes are counted; HTTP/TCP headers,
credentials, client API transport and process isolation are excluded. Runtime is one illustrative host sample
per run, including durable SQLite writes and instrumentation, excluding initialization, offline audits and plots.
It is not production throughput. Raw summaries retain separate request/ACK counts, errors and retries.</p>
<h2>What the graph measures</h2>
<p>The green curve is actual endpoint debtor-side debt after every local event, without smoothing.
An in-flight operation may leave mirrored endpoints temporarily inconsistent. A local hashlock application
is not counted as a completed loop until matching evidence exists at every participant.
The dashed line replays exactly the external obligations incorporated into an offline quote-consistent
shadow ledger, with no clearing. Dependencies that cannot be reconstructed remain pending.
Balance quotes alone do not establish unique causal ordering after an ABA balance repetition.</p>
<p>A transaction can raise debt or reduce it by bilateral netting. Snapshot difference from the no-clearing
reference is not cumulative clearing: later transactions can net differently in the two ledgers.
The CSV separately reports cumulative debt reduction from incorporated completed loops.
Uncleared gross debt includes non-circular debt; zero is generally not an attainable target.</p>
<img src="private-debt-event-detail.png" alt="Transaction and hashlock application effects in the first 2000 messages">
<h2>Policy and completeness</h2>
<p>The new <code>private-local-nonexpansion-v1</code> policy permits original zero-balance trustlines
as comfort-zone headroom, with bilateral preferences and assistance opt-in checked on each edge.
Each participant's two local absolute balances may not increase in sum; the initiator must strictly reduce them.
Summing these local tests counts each edge twice, so a fully applied loop strictly reduces gross debt.
Cancellation uses existing debt edges only. Discovery shuffles eligible local neighbours instead of repeatedly
choosing the lexicographically first dead end. The original comfort policy is retained as a negative control.</p>
<p>The first headroom result used more messages and ended with more debt than cancellation.
The three-run followup filters a continuation before forwarding when the receiving node's two-edge
test would already reject it. It still chooses uniformly among all eligible neighbours, uses the
same hash-bound consent policy, and rechecks quotes at prepare. These are paired development runs on
the same seeds, not held-out validation. All seven original runs and all three followup runs are retained.</p>
<p><strong>This is not a completeness or maximum-clearing proof.</strong> A five-edge loop with marginal gross-debt
changes −1, −1, −1, +1, +1 is globally improving, but the participant between the two helper edges would
increase its local exposure and refuses this policy. More retries cannot overcome that consent restriction.
Discovering every remaining admissible loop also requires a liveness argument under concurrent searches.
Privacy-preserving aggregate consent and distributed conflict recovery remain research work.</p>
<p>The following global diagnostic runs only after measurement and is never supplied to participants.
Each true entry has an explicit remaining one-unit cycle witness in
<a href="residual-diagnostics.json">residual-diagnostics.json</a>. A beneficial headroom witness may
require consent beyond the present local nonexpansion policy; it is not a private discovery result.</p>
<table><tr><th>Method</th><th>Workload</th><th>Debt cycle remains</th><th>Improving headroom cycle remains</th></tr>{residual_table}</table>
<p>In these measurements, all three filtered runs still have a witnessed improving headroom loop
that satisfies the current local nonexpansion rule. Seeds 602 and 603 also retain ordinary debt cycles.
Thus the observed remaining gap includes finite-window discovery limits, separately from the
five-edge counterexample demonstrating the policy's general incompleteness.</p>
<h2>Workload and limits</h2>
<ul><li>Three frozen 32-node / 96-trustline graphs, seeds 601–603; signed initial balances −3…3.
All original trustlines have broad bilateral comfort and credit intervals ±10,000 TEST and assistance enabled.</li>
<li>1,000 independently scheduled Poisson offers per graph, rate 25 per simulated time unit,
uniform original trustline, signed sizes ±1, ±2, ±3. Offers use actual bilateral proposal/approval/commit messages.</li>
<li>Independent exponential actor wakeups with mean 1; one-way simulated delays uniform 0.005…0.015;
retry delay 0.05. Each actor stops new discovery 30 time units after the last offer.
Observation ends 10 units later; no forced unlock or hidden queue-empty drain.
A 250,000-request safety cap retains censored/pending work.</li>
<li>Honest, stable identities; reliable delivery in these ten measurements.
Focused tests cover selected loss/retry cases, not Byzantine security, permanent-loss recovery or deployment readiness.
Shared opaque hashes and timing may reveal correlations; neighbour-private contents do not mean traffic anonymity.</li>
<li>Actual SHA-256 context-bound preimages, immutable local approvals, reservations, durable outbox/inbox,
and separate SQLite WAL/FULL databases. Automatic local approvals are a simulation policy; the user's running demo is unchanged.</li></ul>
<img src="private-debt-all-seeds.png" alt="All nine primary and followup traces">
<h2>Validation and versions</h2>
<p>Independent replay: see <a href="independent-audit.json">audit results</a>.
The 116-test MDG2 benchmark suite and 111-test app suite passed.
Python {data['python']}; SQLite {data['sqlite']}; plotting matplotlib {matplotlib.__version__}.
The exact source/input SHA-256 pins are in <a href="source-freeze.json">source-freeze.json</a>.
Raw gzip journals contain every measured event and exact credential-free message body.
Fresh cryptographic secrets and receipt timestamps are not seeded; seeded fixtures and routing choices do not
imply byte-identical output on replay.</p>
<p>The earlier 100% benchmark is a <strong>coordinated exact reference</strong>, with membership/path knowledge
and serialized epochs. It does not establish the privacy or coordinator-free claims tested here.</p>
"""
    (OUT / 'report.html').write_text(report)
    (OUT / 'source-freeze.json').write_text(json.dumps(data['freeze'], indent=2)+'\n')
    (OUT / 'filtered-source-freeze.json').write_text(json.dumps(followup['freeze'], indent=2)+'\n')
    post_names = ['build_private_stream_report.py', 'audit_private_campaign.py',
                  'private_stream_post_audit.py', 'private_residual_diagnostic.py',
                  'test_private_residual_diagnostic.py']
    (OUT / 'postprocessing-source-manifest.json').write_text(json.dumps(dict(
        scope='Post-measurement validation and rendering only; actor inputs and measured source pins unchanged.',
        sources={f'experiments/mdg2/{name}': hashlib.sha256(
            (ROOT/'experiments/mdg2'/name).read_bytes()).hexdigest() for name in post_names}),
        indent=2)+'\n')
    (OUT / 'REPRODUCE.txt').write_text(
        'From the repository root, with the pinned files present:\n'
        'python -m unittest discover -s experiments/mdg2 -p "test_private*.py" -q\n'
        'python experiments/mdg2/private_stream_benchmark.py --run\n'
        'python experiments/mdg2/private_filter_benchmark.py --run\n'
        'python experiments/mdg2/audit_private_campaign.py\n'
        'python experiments/mdg2/build_private_stream_report.py\n'
        'The runner checks the prospective freeze and resumes existing matching evidence.\n')
    with zipfile.ZipFile(OUT / 'private-clearing-graphs.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('private-debt-vs-messages.png', 'private-debt-event-detail.png',
                     'private-debt-all-seeds.png', 'private-debt-vs-messages.pdf',
                     'summary.csv', 'summary.json', 'report.html', 'independent-audit.json',
                     'residual-diagnostics.json', 'source-freeze.json', 'filtered-source-freeze.json',
                     'postprocessing-source-manifest.json', 'REPRODUCE.txt'):
            archive.write(OUT/name, name)
    files = sorted(p for p in OUT.iterdir() if p.is_file() and p.name != 'SHA256SUMS')
    (OUT / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in files))
    print(OUT / 'report.html')


if __name__ == '__main__':
    main()
