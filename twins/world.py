"""Observable ecology. All distances are normalized; the arena is 180 mm wide.

Body collision and optical occlusion are geometric approximations. The predator
has no access to neural arrays or to positions hidden from its sensors.
"""
from __future__ import annotations
import math
import numpy as np

WORLD_DT = .02
WORLD_MM = 180.

def angle(x):
    return (float(x) + math.pi) % (2 * math.pi) - math.pi

def clip(x, a=0., b=1.):
    return float(np.clip(x, a, b))

def intersects(a, b, wall, margin=0.):
    """Closed segment vs axis-aligned rectangle; handles collinear segments."""
    lo, hi = 0., 1.
    for axis, key, size in ((0, "x", "w"), (1, "y", "h")):
        start, delta = a[axis], b[axis] - a[axis]
        minimum, maximum = wall[key] - margin, wall[key] + wall[size] + margin
        if abs(delta) < 1e-12:
            if not minimum <= start <= maximum:
                return False
        else:
            enter, leave = sorted(((minimum - start) / delta, (maximum - start) / delta))
            lo, hi = max(lo, enter), min(hi, leave)
            if lo > hi:
                return False
    return True

def visible(a, b, walls):
    return not any(intersects(a, b, wall) for wall in walls)

def move_collision(x, y, nx, ny, walls, radius=.008):
    nx, ny = clip(nx, radius, 1 - radius), clip(ny, radius, 1 - radius)
    if any(intersects((x, y), (nx, ny), wall, radius) for wall in walls):
        # Sliding contact; no teleportation through thin barriers.
        if not any(intersects((x, y), (nx, y), wall, radius) for wall in walls):
            return nx, y, True
        if not any(intersects((x, y), (x, ny), wall, radius) for wall in walls):
            return x, ny, True
        return x, y, True
    return nx, ny, False

class World:
    def __init__(self, seed=42):
        self.rng = np.random.default_rng(seed + 9187)
        self.tick = 0
        self.mouse_enabled = True
        self.mouse_static = False
        self.partner_mask = [False, False]
        self.predator_mask = [False, False]
        self.visual_disabled = [False, False]
        self.obstacles = [
            {"id": "screen", "x": .49, "y": .10, "w": .025, "h": .27, "height": .13},
            {"id": "block", "x": .60, "y": .72, "w": .10, "h": .10, "height": .09}]
        self.refuges = [{"id": "refuge", "x": .10, "y": .76, "w": .20, "h": .14, "height": .025}]
        self.food = [{"x": .18, "y": .23, "radius": .035}, {"x": .82, "y": .78, "radius": .025}]
        self.heat_zones = [{"x": .83, "y": .22, "radius": .085, "intensity": .7}]
        self.heat_enabled = False
        self.pulse = [0., 0.]
        self.odor = [0., 0.]
        self.mouse = dict(x=.78, y=.36, heading=math.pi, speed=0., energy=1.,
                          target=None, confidence=0., state="Explore", attention=0.,
                          last_seen=None, lost_ticks=0, sniff_phase=0., trail=[])
        self.last_positions = [[.31, .50], [.64, .49]]
        self.velocities = [0., 0.]
        self.observations = [{}, {}]

    def sense_mouse(self, bodies):
        mouse = self.mouse
        own = (mouse["x"], mouse["y"])
        sensed = []
        for i, body in enumerate(bodies):
            point = (body.x, body.y)
            distance = math.dist(own, point)
            relative = angle(math.atan2(point[1]-own[1], point[0]-own[0])-mouse["heading"])
            sheltered = any(intersects(point, point, r) for r in self.refuges)
            if distance < .65 and abs(relative) < 2.35 and visible(own, point, self.obstacles) and not sheltered:
                confidence = clip((1-distance/.65) * (.7 + min(.3, self.velocities[i]*200)))
                sensed.append((confidence, i, [float(body.x), float(body.y)]))
        return sensed

    def update_mouse(self, bodies):
        mouse = self.mouse
        if not self.mouse_enabled:
            mouse.update(state="Removed", target=None, speed=0., confidence=0.)
            return
        if self.mouse_static:
            mouse.update(state="Static control", speed=0., target=None)
            return
        sensed = self.sense_mouse(bodies)
        goal = None
        if sensed:
            confidence, target, goal = max(sensed)
            mouse.update(target=target, confidence=confidence, last_seen=goal, lost_ticks=0)
            distance = math.dist((mouse["x"], mouse["y"]), goal)
            mouse["state"] = "Chase" if distance < .34 else "Approach"
            speed = .0026 if distance < .34 else .0015
        elif mouse["last_seen"] is not None and mouse["lost_ticks"] < 100:
            mouse.update(state="Search", target=None, confidence=mouse["confidence"]*.97)
            mouse["lost_ticks"] += 1
            goal, speed = mouse["last_seen"], .0011
        else:
            mouse.update(state="Explore", target=None, confidence=0., last_seen=None)
            speed = .0009
        if mouse["energy"] < .25:
            mouse["state"], speed = "Rest", 0.
        if mouse["state"] == "Rest":
            mouse["energy"] = min(1., mouse["energy"] + .012)
        else:
            mouse["energy"] = max(0., mouse["energy"] - .0004)
        desired = math.atan2(goal[1]-mouse["y"], goal[0]-mouse["x"]) if goal else mouse["heading"] + float(self.rng.normal(0., .13))
        mouse["heading"] = angle(mouse["heading"] + clip(angle(desired-mouse["heading"]), -.14, .14))
        mouse["speed"] += (speed-mouse["speed"])*.18
        nx, ny = mouse["x"] + math.cos(mouse["heading"])*mouse["speed"], mouse["y"] + math.sin(mouse["heading"])*mouse["speed"]
        mouse["x"], mouse["y"], collision = move_collision(mouse["x"], mouse["y"], nx, ny, self.obstacles+self.refuges, .06)
        if collision:
            mouse["heading"] = angle(mouse["heading"] + .65)
            mouse["speed"] *= .3
        mouse["sniff_phase"] += .4
        mouse["attention"] = mouse["confidence"]
        mouse["trail"] = (mouse["trail"] + [{"x": mouse["x"], "y": mouse["y"]}])[-200:]

    def observe(self, index, bodies):
        body, partner = bodies[index], bodies[1-index]
        own, other = (body.x, body.y), (partner.x, partner.y)
        mouse = (self.mouse["x"], self.mouse["y"])
        distance = math.dist(own, mouse)
        bearing = angle(math.atan2(mouse[1]-own[1], mouse[0]-own[0])-body.heading)
        m_visible = bool(self.mouse_enabled and not self.predator_mask[index] and
                         not self.visual_disabled[index] and distance < .65 and abs(bearing) < 2.7 and
                         visible(own, mouse, self.obstacles))
        partner_distance = math.dist(own, other)
        p_visible = bool(not self.partner_mask[index] and not self.visual_disabled[index] and
                         partner_distance < .65 and visible(own, other, self.obstacles))
        partner_bearing = angle(math.atan2(other[1]-own[1], other[0]-own[0])-body.heading)
        old = self.observations[index]
        angular_size = 2*math.atan(.07/max(distance,.01)) if m_visible else 0.
        looming = clip((angular_size-old.get("angular_size", angular_size))/.08) if m_visible else 0.
        motion = clip(self.velocities[1-index]*220) if p_visible else 0.
        visual = clip(angular_size*.65 + looming*.7) if m_visible else 0.
        odor = max(clip(1-math.dist(own,(f["x"],f["y"]))/.3) for f in self.food)
        thermal = max((clip(1-math.dist(own,(z["x"],z["y"]))/z["radius"])*z["intensity"] for z in self.heat_zones), default=0.) if self.heat_enabled else 0.
        contact = float(self.mouse_enabled and distance < .07)
        o = dict(predator_visible=m_visible, partner_visible=p_visible, predator_distance=distance,
                 predator_bearing=bearing, partner_bearing=partner_bearing,
                 partner_distance=partner_distance, partner_motion=motion, angular_size=angular_size,
                 looming=looming, visual_input=visual, food_odor=odor,
                 nociceptive_input=max(thermal, self.pulse[index]), contact=contact)
        sensory = np.zeros(16, np.float32)
        # Two visual hemi-fields encode observable shape/motion, not social labels.
        for magnitude, direction in ((visual,bearing),(motion*.45,partner_bearing)):
            sensory[8] += magnitude*(.5+.5*math.sin(direction))
            sensory[9] += magnitude*(.5-.5*math.sin(direction))
        sensory[10] = odor*.3 + self.odor[index]
        sensory[11] = o["nociceptive_input"]
        sensory[12] = contact*.35
        return o, sensory

    def before(self, bodies):
        self.tick += 1
        self.update_mouse(bodies)
        values = [self.observe(i,bodies) for i in range(2)]
        self.observations = [v[0] for v in values]
        return [v[1] for v in values]

    def after(self, bodies):
        for i, body in enumerate(bodies):
            self.velocities[i] = math.dist(self.last_positions[i], (body.x,body.y))
            self.last_positions[i] = [float(body.x),float(body.y)]

    def snapshot(self):
        return dict(tick=self.tick, seconds=self.tick*WORLD_DT, width_mm=WORLD_MM,
                    mouse={**self.mouse, "enabled":self.mouse_enabled, "brain_model":False,
                           "controller":"Observable-state predator policy", "speed_mm_s":self.mouse["speed"]*WORLD_MM/WORLD_DT},
                    obstacles=self.obstacles, refuges=self.refuges, food=self.food,
                    heat_zones=self.heat_zones if self.heat_enabled else [],
                    observations=self.observations,
                    visibility_masks=dict(predator=self.predator_mask,partner=self.partner_mask,visual=self.visual_disabled),
                    provenance={"geometry":"HEURISTIC","mouse":"AGENT_POLICY","observations":"DERIVED"})
