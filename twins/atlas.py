"""Stable anatomical level of detail. Positions are source anchors, not neuron meshes."""
import numpy as np

class Atlas:
    def __init__(self,engine,limit=30000):
        graph=engine.graph
        positions=getattr(graph,"positions",None)
        if positions is None or not np.isfinite(positions).all(axis=1).any():
            self.indices=np.array([],dtype=int)
            self.data=dict(available=False,reason="This fixture has no anatomical coordinates.",nodes=[],edges=[])
            return
        valid=np.flatnonzero(np.isfinite(positions).all(axis=1))
        self.indices=valid[np.linspace(0,len(valid)-1,min(limit,len(valid)),dtype=int)]
        coords=positions[self.indices]
        regions=sorted(set(graph.regions))
        nodes=[dict(index=int(index),id=str(graph.ids[index]),
                    p=[round(float(x),3) for x in coords[k]],
                    region=regions.index(graph.regions[index]),
                    cell_class=str(graph.classes[index]) if getattr(graph,"classes",None) else "")
               for k,index in enumerate(self.indices)]
        local=engine.matrix[self.indices][:,self.indices].tocoo()
        strongest=np.argsort(-np.abs(local.data),kind="stable")[:1500]
        edges=[[int(local.col[k]),int(local.row[k]),round(float(local.data[k]),3)] for k in strongest]
        self.data=dict(available=True,nodes=nodes,edges=edges,regions=regions,
                       total=engine.n,positioned=len(valid),sample=len(nodes),units="micrometres",
                       kind="FlyWire annotated 3D anchors; straight edges show connectivity, not neurite trajectories",
                       source_commit=graph.metadata.get("annotation_commit"),
                       provenance="ANATOMICAL_DATA")

    def activity(self,engine):
        indices=self.indices[::max(1,len(self.indices)//2000)]
        return dict(tick=engine.tick,indices=indices.tolist(),
                    a=np.round(engine.agents[0].trace[indices],3).tolist(),
                    b=np.round(engine.agents[1].trace[indices],3).tolist())
