"""Persistent laboratory combining a real sparse graph with engineered embodiment."""
from __future__ import annotations
from collections import deque
import math
import numpy as np
from .engine import Experiment, NEURAL_STEPS_PER_TICK
from .world import World, WORLD_DT, WORLD_MM, angle, clip, move_collision
from .protocols import protocol_spec

class Laboratory(Experiment):
    def __init__(self, seed=42, plasticity=True, graph=None):
        super().__init__(seed=seed,plasticity=plasticity,graph=graph)
        self.world = World(seed)
        for i,a in enumerate(self.agents):
            a.x,a.y = self.world.last_positions[i]
            a.heading = 0. if i == 0 else math.pi*.1
        self.experiment = protocol_spec("free")
        self.experiment_start = 0
        self.mode = "world"
        self.internal = [self._internal(),self._internal()]
        self.world_history = deque(maxlen=600)
        self.motion_record = []
        self.replay_motion = None
        self.motion_cursor = 0
        self._init_plasticity()

    @staticmethod
    def _internal():
        return dict(threat=0.,arousal=0.,nociception=0.,sensitization=0.,hunger=.15,
                    fatigue=0.,dopamine=0.,octopamine=0.,serotonin=0.,
                    visual_rate=0.,descending_rate=0.,memory_rate=0.,baseline_visual=0.,
                    speed_mm_s=0.,behaviour="rest",reward=0.)

    def _init_plasticity(self):
        # Actual edges incident to the annotated memory population, capped for CPU.
        rows=self.ports["memory"]
        sub=self.matrix[rows].tocoo()
        order=np.argsort(-np.abs(sub.data),kind="stable")[:4096]
        self.plastic_pre=sub.col[order].astype(np.int32)
        self.plastic_post=rows[sub.row[order]].astype(np.int32)
        self.plastic_base=sub.data[order].copy()
        for a in self.agents:
            a.plastic_delta=np.zeros(len(order),np.float32)
            a.plastic_eligibility=np.zeros(len(order),np.float32)

    def configure(self, spec):
        base=protocol_spec(spec["id"])
        for key in ("onset","offset","duration","intensity"):
            if key in spec: base[key]=spec[key]
        if not 0 <= base["onset"] < base["offset"] <= base["duration"] <= 20000:
            raise ValueError("Require 0 <= onset < offset <= duration <= 20000")
        if not 0 <= base["intensity"] <= 1:
            raise ValueError("Intensity must be between 0 and 1")
        self.experiment,self.experiment_start=base,self.tick
        self.mode="learning" if base["id"]=="learning" else "world"
        self.completed=False
        self.world.predator_mask=["predator-mask-a" in base["conditions"],False]
        self.world.partner_mask=["partner-mask-a" in base["conditions"],False]
        self.world.visual_disabled=["visual-off-a" in base["conditions"],False]
        self.world.mouse_static="static" in base["conditions"]
        self.world.heat_enabled=base["id"]=="zone"
        self.replay_motion=None
        if self.mode=="learning":
            self.set_phase("baseline")
        self._event("protocol",base["title"],protocol=base)

    def _protocol_tick(self):
        elapsed=self.tick-self.experiment_start
        spec=self.experiment
        on=spec["onset"] <= elapsed < spec["offset"]
        if spec["id"]=="habituation": on=on and elapsed%40<20
        self.world.mouse_enabled=(spec["id"]=="free" or on) and "no-mouse" not in spec["conditions"]
        self.world.pulse=[0.,spec["intensity"] if on and spec["id"] in ("nociception","odor") else 0.]
        self.world.odor=[0.,spec["intensity"] if (on or elapsed>=spec["duration"]-40) and spec["id"]=="odor" else 0.]
        if elapsed in (spec["onset"],spec["offset"]) and spec["id"]!="free":
            self._event("stimulus_on" if on else "stimulus_off","Exposure onset" if on else "Exposure offset")
        if self.replay_motion is not None:
            self.world.mouse_enabled=False

    def _neural_step(self,agent,sensory):
        if hasattr(agent,"plastic_delta"):
            extra=np.bincount(self.plastic_post, weights=agent.plastic_delta*agent.spikes[self.plastic_pre],
                              minlength=self.n).astype(np.float32)
            # Extra current participates in membrane integration; never edits body.
            original=self.background
            self.background=original+extra
            try: super()._neural_step(agent,sensory)
            finally: self.background=original
        else: super()._neural_step(agent,sensory)

    def _internal_step(self,i,sensory):
        a,s=self.agents[i],self.internal[i]
        visual=float(a.trace[np.concatenate(self.ports["sensory"][8:10])].mean())
        memory=float(a.trace[self.ports["memory"]].mean())
        noc=float(a.trace[self.ports["sensory"][11]].mean())
        descending=float(a.trace[np.concatenate((self.ports["left"],self.ports["right"]))].mean())
        s["baseline_visual"] += .012*(visual-s["baseline_visual"])
        response=max(0.,visual-s["baseline_visual"])
        s["threat"]=clip(s["threat"]*.96+.025*math.tanh(response))
        s["arousal"]=clip(s["arousal"]*.97+.018*math.tanh(response+memory*.05))
        s["nociception"]=clip(s["nociception"]*.94+.016*math.tanh(noc))
        s["sensitization"]=clip(s["sensitization"]*.998+.001*s["nociception"])
        s["dopamine"]=float(s["reward"]-sensory[11]*.4)
        s["octopamine"]=s["arousal"]
        s["serotonin"]=s["fatigue"]
        s["hunger"]=clip(s["hunger"]+.0001-sensory[10]*.0004)
        s["visual_rate"],s["memory_rate"],s["descending_rate"]=visual*50,memory*50,descending*50
        if self.plasticity and not self.neural_silenced:
            pre,post=self.plastic_pre,self.plastic_post
            eligibility=a.spikes[post]*a.trace[pre]-a.spikes[pre]*a.trace[post]*.8
            a.plastic_eligibility*=.96
            a.plastic_eligibility+=eligibility*.04
            delta=.004*s["dopamine"]*a.plastic_eligibility
            bound=np.maximum(np.abs(self.plastic_base)*.2,.002)
            a.plastic_delta[:]=np.clip(a.plastic_delta+delta,-bound,bound)

    def _world_body(self,i):
        a,s=self.agents[i],self.internal[i]
        left=float(a.trace[self.ports["left"]].mean())
        right=float(a.trace[self.ports["right"]].mean())
        old=(a.x,a.y)
        a.heading=angle(a.heading+.13*math.tanh((right-left)*3))
        speed=.0018*math.tanh((left+right)*.5)
        a.x,a.y,collision=move_collision(a.x,a.y,a.x+math.cos(a.heading)*speed,
                                        a.y+math.sin(a.heading)*speed,self.world.obstacles)
        if collision: a.heading=angle(a.heading+.35)
        s["speed_mm_s"]=math.dist(old,(a.x,a.y))*WORLD_MM/WORLD_DT
        s["fatigue"]=clip(s["fatigue"]*.995+speed*.8)
        s["behaviour"]="locomotion" if s["speed_mm_s"]>.1 else "rest"
        a.energy=clip(1-s["hunger"]-s["fatigue"]*.2)
        a.trail.append({"x":a.x,"y":a.y})
        if self.world.observations[i].get("food_odor",0)>.8:
            s["reward"]=.3
        else: s["reward"]=0.

    def step(self,n=1):
        if self.mode=="learning": return super().step(n)
        if type(n) is not int or not 1<=n<=10000: raise ValueError("Invalid step count")
        for _ in range(n):
            if self.completed: break
            self.tick+=1
            self._protocol_tick()
            if self.replay_motion is not None and self.motion_cursor<len(self.replay_motion):
                b=self.agents[1]; point=self.replay_motion[self.motion_cursor]
                b.x,b.y,b.heading=point
                self.motion_cursor+=1
            inputs=self.world.before(self.agents)
            for i,a in enumerate(self.agents):
                s=self.internal[i]
                # Slow internal variables modulate sensory excitability.
                inputs[i]*=1+.35*s["arousal"]+.15*s["sensitization"]
                inputs[i][:8]+=.11*(1-.4*s["fatigue"])
                self._neural_step(a,inputs[i])
                self._internal_step(i,inputs[i])
            for i in range(2):
                if not (i==1 and self.replay_motion is not None): self._world_body(i)
            self.world.after(self.agents)
            b=self.agents[1]
            self.motion_record.append([b.x,b.y,b.heading])
            self.motion_record=self.motion_record[-20000:]
            if self.tick%5==0:
                self._record_history()
                self.world_history.append(self.telemetry())
            if self.experiment["id"]!="free" and self.tick-self.experiment_start>=self.experiment["duration"]:
                self.completed=True
                self._event("complete","Protocol complete. Evaluate observed effects against controls.")
        return self.snapshot()

    def telemetry(self):
        return dict(tick=self.tick,seconds=self.tick*WORLD_DT,
                    a={**self.internal[0],**self.world.observations[0]},
                    b={**self.internal[1],**self.world.observations[1]},
                    mouse_state=self.world.mouse["state"],divergence=self._divergence()[0])

    def snapshot(self):
        result=super().snapshot()
        if not hasattr(self,"world"): return result
        result.update(world=self.world.snapshot(),world_history=list(self.world_history),
                      experiment={**self.experiment,"elapsed":self.tick-self.experiment_start},
                      mode=self.mode,world_seconds=self.tick*WORLD_DT)
        result["protocol"]["completed"]=self.completed
        for i,t in enumerate(result["twins"]):
            t["internal"]=self.internal[i].copy()
            t["plastic_synapses"]=len(self.plastic_pre)
            t["plastic_delta_l2"]=float(np.linalg.norm(self.agents[i].plastic_delta))
        return result

    def command(self,action,**kwargs):
        value=kwargs.get("value")
        if action=="experiment": self.configure(value)
        elif action=="mouse":
            self.world.mouse_enabled=bool(value)
            self._event("intervention","Predator inserted" if value else "Predator removed")
            # Manual intervention overrides automatic mouse schedule.
            self.experiment=protocol_spec("free")
            if not value: self.experiment["conditions"]=["no-mouse"]
        elif action=="phase":
            self.mode="learning"
            return super().command(action,**kwargs)
        else: return super().command(action,**kwargs)
        return self.snapshot()
