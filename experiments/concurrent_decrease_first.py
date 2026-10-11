"""Fixed local decrease-first residual search; unchanged concurrent settlement."""
from concurrent_headroom import ConcurrentHeadroom, ResidualNode, Proposal


class DecreaseFirstNode(ResidualNode):
    def search(self, token):
        if token.hops>=self.sim.search_budget:
            self.finish(token)
            return
        candidates=[(p,d) for p in self.episodes for d in (1,-1) if (p,d) not in token.tried[-1] and self.capacity(p,d)>0 and not self.locked(p)]
        self.sim.random.shuffle(candidates)
        candidates.sort(key=lambda arc: (arc[1] != 1, -self.capacity(*arc)))
        for peer,direction in candidates:
            token.tried[-1].add((peer,direction))
            ep=self.episodes[peer]
            arc=(self.name,peer,direction,self.capacity(peer,direction),ep.number,ep.revision)
            if peer in token.path:
                start=token.path.index(peer)
                arcs=token.arcs[start:]+[arc]
                if len(arcs)<3 or sum(a[2] for a in arcs)<=0:
                    continue
                tx=Proposal(token,token.path[start:],arcs,min(a[3] for a in arcs),proposed_at=self.sim.time)
                self.sim.metrics['proposals']+=1
                self.sim.send(self.name,peer,'hprepare',tx)
                return
            if len(token.path)<self.sim.max_hops:
                token.path.append(peer);token.arcs.append(arc);token.tried.append(set())
                token.visited.add(peer);token.hops+=1
                self.sim.send(self.name,peer,'hstep',token)
                return
        if len(token.path)>1:
            token.path.pop();token.arcs.pop();token.tried.pop();token.hops+=1
            self.sim.send(self.name,token.path[-1],'hstep',token)
        else:
            self.active=False
            self.sim.metrics['exhausted_searches']+=1


class DecreaseFirstHeadroom(ConcurrentHeadroom):
    def _post(self,a,b,amount,requested):
        for name in (a,b):
            if name not in self.nodes:
                self.nodes[name]=DecreaseFirstNode(name,self)
                if self.searches_enabled:
                    self.schedule(self.time+self.random.randrange(self.retry_interval),name,'wake',None)
        super()._post(a,b,amount,requested)
