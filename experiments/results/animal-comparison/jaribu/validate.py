import sys,json,hashlib
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
p=Path(sys.argv[1]); out=Path(sys.argv[2]); balances={};net=defaultdict(int)
for l in p.read_text().splitlines():
 u,v,a=l.split();a=int(Decimal(a)*1000);balances[u,v]=balances.get((u,v),0)+a;net[u]-=a;net[v]+=a
initial=sum(balances.values());total=0;n=0
for l in Path(str(out)+'.cycles').read_text().splitlines():
 *nodes,a=l.split();a=int(Decimal(a)*1000)
 assert len(nodes)==len(set(nodes)),('non simple',n,nodes)
 assert len(nodes)>=3 and a>0,(n,nodes,a)
 for u,v in zip(nodes,nodes[1:]+nodes[:1]):
  assert balances.get((u,v),0)>=a,(n,u,v,a,balances.get((u,v),0))
  balances[u,v]-=a
 total+=a*len(nodes);n+=1
newnet=defaultdict(int)
for (u,v),a in balances.items():newnet[u]-=a;newnet[v]+=a
assert dict(net)==dict(newnet)
s=json.loads(Path(str(out)+'.summary.json').read_text());assert n==s['loops']
# Independent Kahn check: zero remaining directed cycles means cancellation saturation.
adj=defaultdict(list); indegree={u:0 for u in net}
for (u,v),a in balances.items():
 if a>0: adj[u].append(v); indegree[v]+=1
ready=[u for u,d in indegree.items() if d==0]; seen=0
while ready:
 u=ready.pop();seen+=1
 for v in adj[u]:
  indegree[v]-=1
  if indegree[v]==0: ready.append(v)
summary={**s,'residualIsAcyclic':seen==len(indegree),'inputSHA256':hashlib.sha256(p.read_bytes()).hexdigest(),'validatedLoops':n,'cleared':total/1000,'initial':initial/1000,'percent':100*total/initial,'conservedNetPositions':True,'remaining':sum(balances.values())/1000}
Path(str(out)+'.validated.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
