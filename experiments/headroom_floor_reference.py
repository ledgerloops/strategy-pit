"""Offline static price of one-unit lower bounds; never an online algorithm."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform

from temporal_reference import min_residual
from temporal_sarafu import load_sarafu, net_graph


def net(graph):
    result=Counter()
    for (a,b),value in graph.items():
        result[a]-=value
        result[b]+=value
    return {node:value for node,value in result.items() if value}


def floor_reference(caps, floor=1):
    if type(floor) is not int or floor<0 or any(value<floor for value in caps.values()):
        raise ValueError('floor must be an integer within every capacity')
    shifted={edge:value-floor for edge,value in caps.items() if value>floor}
    result=min_residual(shifted)
    residual={tuple(row[:2]):row[2] for row in result['residual']}
    final={edge:floor+residual.get(edge,0) for edge in caps}
    # Independent reconstruction in the original, unshifted constraint system.
    assert all(floor<=value<=caps[edge] for edge,value in final.items())
    assert net(final)==net(caps)
    assert sum(final.values())==result['minimum_final_debt_scaled']+floor*len(caps)
    return {'floor_scaled':floor,'status':result['status'],
            'minimum_final_debt_scaled':sum(final.values()),
            'cleared_scaled':sum(caps.values())-sum(final.values()),
            'primal_bounds_and_net_verified':True,
            'residual':[[a,b,v] for (a,b),v in sorted(final.items()) if v]}


def run(csv_path):
    import ortools
    fixture=load_sarafu(csv_path)
    caps=net_graph(fixture.events)
    baseline=floor_reference(caps,0)
    floored=floor_reference(caps,1)
    gap=floored['minimum_final_debt_scaled']-baseline['minimum_final_debt_scaled']
    paths=[Path(__file__),Path(__file__).with_name('temporal_reference.py'),
           Path(__file__).with_name('temporal_sarafu.py')]
    return {'complete':True,'model':'offline static fixed-cap MCF; chronology ignored',
            'input_sha256':hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
            'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            'python':platform.python_version(),'ortools':ortools.__version__,
            'amount_scale':1000,'events':len(fixture.events),'edges':len(caps),
            'original_debt_scaled':sum(caps.values()),'no_floor':baseline,'one_unit_floor':floored,
            'floor_optimum_cost_scaled':gap,'cost_over_original_debt_percent':100*gap/sum(caps.values()),
            'cost_over_sum_floors':gap/len(caps)}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--csv',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    Path(args.output).write_text(json.dumps(run(args.csv),indent=2)+'\n')
