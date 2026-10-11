"""Version 1 offline temporal exposures; never inputs to protocol decisions.

U(H) integrates requested-but-unposted transfer amounts. K(H) integrates amounts
of individually committed edges until the last leg restores a complete cycle.
K is staged bookkeeping exposure, not financial risk or a feasible alternate
ledger. Do not add these metrics into an invented optimization score. All events
at horizon H are included in endpoint readings; same-tick changes have zero area.
"""
from collections import Counter, defaultdict, deque


def _complete_cycle(entries):
    amounts={-e['delta'] for e in entries}
    outgoing={e['source']:e['target'] for e in entries}
    if len(amounts)!=1 or len(outgoing)!=len(entries):
        raise ValueError('Inconsistent or repeated commit legs')
    if len(set(outgoing.values()))!=len(entries):
        raise ValueError('Repeated receiving node in commit legs')
    if set(outgoing)!=set(outgoing.values()):
        return False
    if len(entries)<3:
        raise ValueError('Cycle must have at least three participants')
    start=next(iter(outgoing))
    visited=set()
    cursor=start
    while cursor not in visited:
        visited.add(cursor)
        cursor=outgoing[cursor]
    if cursor!=start or len(visited)!=len(entries):
        raise ValueError('Disconnected settlement cycles')
    return True


def temporal_exposure(sim, arrivals, horizon, *, allow_incomplete=False):
    """Supplement an independently audited ledger with time-dependent quantities.

    Default requires every external transfer and every started commit cycle to
    complete in the supplied trace. allow_incomplete retains censored backlog
    and unfinished committed amounts through max(horizon,simulator time,last recorded event).
    It does not guess when a missing transfer or cycle will complete.
    """
    if horizon<0:
        raise ValueError('Nonnegative horizon required')
    requests=defaultdict(deque)
    for event in arrivals:
        requests[frozenset((event.source,event.target))].append(event)
    commits=defaultdict(list)
    end=max([horizon,getattr(sim,'time',horizon)]+[r['time'] for r in sim.ledger_records])
    backlog_area=full_delay_area=unposted_amount=0
    postings=[]
    previous=-1
    gap=Counter()
    for record in sim.ledger_records:
        at,a,b,delta=record['time'],record['source'],record['target'],record['delta']
        if at<previous:
            raise ValueError('Ledger must be chronological')
        previous=at
        if record['kind']=='transfer':
            pending=requests[frozenset((a,b))]
            if not pending:
                raise ValueError('Transfer has no requested arrival')
            event=pending.popleft()
            if (a,b,delta)!=(event.source,event.target,event.amount) or at<event.time:
                raise ValueError('Transfer order or amount differs from arrival')
            postings.append((event,at))
        elif record['kind']=='commit':
            if delta>=0:
                raise ValueError('Commit amount must be negative')
            commits[tuple(record['txid'])].append(record)
            if at<=horizon:
                gap[a]-=delta
                gap[b]+=delta
        else:
            raise ValueError('Unknown ledger record kind')
    missing=[event for queue in requests.values() for event in queue]
    if missing and not allow_incomplete:
        raise ValueError('Simulation must drain every external transfer')
    postings.extend((event,None) for event in missing)
    for event,posted in postings:
        stop=end if posted is None else posted
        full_delay_area+=event.amount*max(0,stop-event.time)
        if event.time<=horizon:
            backlog_area+=event.amount*(min(stop,horizon)-event.time)
            if posted is None or posted>horizon:
                unposted_amount+=event.amount
    staged_area=full_staged_area=unfinished_committed_amount=0
    cycle_durations=[]
    pending_cycles=0
    changes=Counter()
    for entries in commits.values():
        complete=_complete_cycle(entries)
        if not complete and not allow_incomplete:
            raise ValueError('Cannot infer completion from partial cycle')
        finish=max(e['time'] for e in entries) if complete else None
        start=min(e['time'] for e in entries)
        if finish is not None:
            cycle_durations.append(finish-start)
        else:
            pending_cycles+=1
        stop=end if finish is None else finish
        for entry in entries:
            at,amount=entry['time'],-entry['delta']
            full_staged_area+=amount*(stop-at)
            if at<=horizon:
                staged_area+=amount*(min(stop,horizon)-at)
                if finish is None or finish>horizon:
                    unfinished_committed_amount+=amount
            # Peak convention is exposure after all events at a timestamp.
            changes[at]+=amount
            if finish is not None:
                changes[finish]-=amount
    exposure=peak=0
    for at in sorted(changes):
        if at>horizon:
            break
        exposure+=changes[at]
        peak=max(peak,exposure)
    assert exposure==unfinished_committed_amount
    return dict(
        metric_version=1,observation_end=end,censored=bool(any(e.time<=end for e in missing) or pending_cycles),
        unposted_transfers_at_trace_end=sum(e.time<=end for e in missing),
        future_requests_beyond_observation=sum(e.time>end for e in missing),unfinished_cycles_at_trace_end=pending_cycles,
        requested_unposted_amount_ticks_to_horizon=backlog_area,
        external_posting_amount_ticks_through_drain=full_delay_area,
        unposted_amount_at_horizon=unposted_amount,
        committed_edge_amount_ticks_awaiting_cycle_completion_to_horizon=staged_area,
        committed_edge_amount_ticks_awaiting_cycle_completion_through_drain=full_staged_area,
        committed_edge_amount_in_unfinished_cycles_at_horizon=unfinished_committed_amount,
        peak_committed_edge_amount_in_unfinished_cycles_to_horizon=peak,
        net_position_gap_l1_against_posted_transfers_at_horizon=sum(abs(v) for v in gap.values()),
        max_first_to_last_commit_ticks=max(cycle_durations,default=0),
        wire_attempts_data_plus_ack=sim.metrics['data_attempts']+sim.metrics['ack_attempts'])
