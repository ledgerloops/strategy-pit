"""Global OFFLINE residual witnesses; never participant or routing inputs.

These static one-unit diagnostics inspect all configured trustlines, including
zero-balance ones. They certify neither private protocol reachability nor a
comfort-constrained global optimum. A headroom witness can require a helper to
increase its two-edge gross exposure; its local-policy eligibility is reported
separately. There is no actor/runtime import or min-cost-flow oracle here.
"""


def _preferences(value):
    fields = ('credit_limit', 'comfort_min', 'comfort_max', 'auto_adjust')
    if not isinstance(value, dict) or any(key not in value for key in fields):
        raise ValueError('Complete bilateral preferences required')
    if any(type(value[key]) is not int or abs(value[key]) > 10**12 for key in fields[:3]):
        raise ValueError('Bounded integer preferences required')
    if value['credit_limit'] < 0 or value['comfort_min'] > value['comfort_max']:
        raise ValueError('Invalid hard limit or comfort interval')
    if type(value['auto_adjust']) is not bool:
        raise ValueError('Boolean auto-adjust required')


def _allowed(before, after, own, peer):
    """Independent bilateral hard-bound/discomfort/opt-in calculation."""
    reducing = (before > 0 and 0 <= after < before) or (before < 0 and before < after <= 0)
    if not reducing and not -peer['credit_limit'] <= after <= own['credit_limit']:
        return False
    low = max(own['comfort_min'], -peer['comfort_max'], -peer['credit_limit'])
    high = min(own['comfort_max'], -peer['comfort_min'], own['credit_limit'])
    if low > high:
        return False
    old, new = max(low-before, before-high, 0), max(low-after, after-high, 0)
    if new > old:
        return False
    return bool(new < old and abs(after) <= abs(before)) or (own['auto_adjust'] and peer['auto_adjust'])


def _cycle(nodes, arcs):
    adjacency = {node: [] for node in nodes}
    for source, target in arcs:
        adjacency[source].append(target)
    color, stack, positions = {}, [], {}
    for start in nodes:
        if color.get(start):
            continue
        # Iterative DFS avoids recursion limits on larger diagnostic graphs.
        color[start] = 1
        positions[start] = len(stack)
        stack.append(start)
        frames = [(start, iter(sorted(adjacency[start])))]
        while frames:
            node, children = frames[-1]
            child = next(children, None)
            if child is None:
                frames.pop(); stack.pop(); positions.pop(node)
                color[node] = 2
            elif color.get(child) == 1:
                return stack[positions[child]:] + [child]
            elif not color.get(child):
                color[child] = 1
                positions[child] = len(stack)
                stack.append(child)
                frames.append((child, iter(sorted(adjacency[child]))))
    return None


def _negative_cycle(nodes, arcs):
    # A virtual zero-cost source reaches every node. An nth-pass decrease
    # witnesses a negative cycle; parents recover an actual directed cycle.
    distance = dict.fromkeys(nodes, 0)
    predecessor = {}
    changed = None
    for _ in nodes:
        changed = None
        for (source, target), arc in sorted(arcs.items()):
            candidate = distance[source] + arc['cost']
            if candidate < distance[target]:
                distance[target] = candidate
                predecessor[target] = source
                changed = target
        if changed is None:
            return None
    if changed is None:
        return None
    for _ in nodes:
        changed = predecessor[changed]
    backward, node = [changed], predecessor[changed]
    while node != changed:
        backward.append(node)
        node = predecessor[node]
    path = list(reversed(backward))
    return path + [path[0]]


def _witness(path, arcs):
    if path is None:
        return None
    changes = []
    local_gross = dict.fromkeys(path[:-1], 0)
    local_net = dict.fromkeys(path[:-1], 0)
    for source, target in zip(path, path[1:]):
        arc = arcs[source, target]
        before, after = arc['before'], arc['after']
        cost = abs(after)-abs(before)
        changes.append(dict(source=source, target=target, before=before, after=after,
                            mirror_before=-before, mirror_after=-after, cost=cost,
                            bilateral_comfort_admissible=arc['admissible']))
        local_net[source] += after-before
        local_net[target] -= after-before
        local_gross[source] += cost
        local_gross[target] += cost
    if len(path) < 4 or any(local_net.values()):
        raise ValueError('Invalid diagnostic cycle witness')
    total = sum(change['cost'] for change in changes)
    return dict(path=path, changes=changes, gross_delta=total, gross_reduction=-total,
                assisted_edges=sum(change['cost'] > 0 for change in changes),
                local_net_delta=local_net, local_gross_delta=local_gross,
                local_nonexpansion_permitted=all(value <= 0 for value in local_gross.values())
                                             and any(value < 0 for value in local_gross.values()))


def diagnose(balances, preferences):
    """Inspect static mirrored balances[node][peer] and own preferences[node][peer].

    Node IDs must be nonempty strings. Preferences normally contain hard grants
    of 10,000; the actual bilateral grants supplied are enforced, not replaced.
    An ordinary positive-debt cycle is topological and may lack fresh consent.
    """
    if any(not isinstance(node, str) or not node for node in balances):
        raise ValueError('Nonempty string node identities required')
    nodes = sorted(balances)
    arcs, debt, admissible, admissible_debt = {}, {}, {}, {}
    for node in nodes:
        for peer, before in sorted(balances[node].items()):
            if peer == node or peer not in balances or node not in balances[peer]:
                raise ValueError('Missing mirrored endpoint or self edge')
            if type(before) is not int or abs(before) > 10**12:
                raise ValueError('Bounded integer local balance required')
            if balances[peer][node] != -before or type(balances[peer][node]) is not int:
                raise ValueError('Non-mirrored final balances: retain endpoint mismatch separately')
            try:
                own, other = preferences[node][peer], preferences[peer][node]
            except KeyError as error:
                raise ValueError('Missing endpoint preferences') from error
            _preferences(own); _preferences(other)
            after = before+1
            allowed = abs(after) <= 10**12 and _allowed(before, after, own, other)
            # Require the exact mirrored move to pass both endpoint calculations.
            allowed = allowed and _allowed(-before, -after, other, own)
            arc = dict(before=before, after=after, cost=abs(after)-abs(before), admissible=allowed)
            arcs[node, peer] = arc
            if before < 0:
                debt[node, peer] = arc
            if allowed:
                admissible[node, peer] = arc
                if before < 0:
                    admissible_debt[node, peer] = arc
    headroom = _witness(_negative_cycle(nodes, admissible), admissible)
    if headroom is not None and headroom['gross_delta'] >= 0:
        raise ValueError('Bellman-Ford returned a non-improving witness')
    return dict(scope='Global offline static diagnostic only; no actor input or private reachability claim.',
                nodes=len(nodes), trustlines=len(arcs)//2,
                gross_debt=sum(abs(value) for node in nodes for peer, value in balances[node].items())//2,
                positive_debt_arcs=len(debt), admissible_unit_arcs=len(admissible),
                positive_debt_cycle=_witness(_cycle(nodes, debt), debt),
                admissible_debt_cycle=_witness(_cycle(nodes, admissible_debt), admissible_debt),
                improving_headroom_cycle=headroom)


def diagnose_edges(edges):
    """Convenience input: (a, b, signed_balance_at_a, a_prefs, b_prefs)."""
    balances, preferences = {}, {}
    for a, b, balance, own, other in edges:
        if b in balances.get(a, {}) or a == b:
            raise ValueError('Duplicate or self trustline')
        balances.setdefault(a, {})[b] = balance
        balances.setdefault(b, {})[a] = -balance
        preferences.setdefault(a, {})[b] = own
        preferences.setdefault(b, {})[a] = other
    return diagnose(balances, preferences)
