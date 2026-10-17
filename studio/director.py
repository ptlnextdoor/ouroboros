"""Demo director: drives the LIVE Fusion viewport (on screen, not offscreen captures) so a
screen recording shows the jet framed and changing while FORGE Studio streams a turn.

Each beat: activate MJ1, set visibility, orbit the real camera smoothly, fit.
Run: /opt/miniconda3/bin/python3 studio/director.py
"""
import json
import sys
import time

sys.path.insert(0, "/Users/aayu/Workspace/developer/recursive-agents-hack")
from studio import fusion  # noqa: E402

SETUP = r'''
import adsk.core, adsk.fusion, json
app = adsk.core.Application.get()
for i in range(app.documents.count):
    d = app.documents.item(i)
    if d.name.startswith("MJ1"):
        d.activate(); break
des = adsk.fusion.Design.cast(app.activeProduct)
root = des.rootComponent
def setvis(occs, skin_on):
    for o in occs:
        n = o.name
        if n.startswith("MJ1_KC:") or n.startswith("MJ1_KC "):
            o.isLightBulbOn = True
        elif n.startswith(("FUSELAGE", "WING", "FIN", "POD_", "ENGINE_", "MJ1_NATIVE", "MJ1_KC_AR")):
            o.isLightBulbOn = False
        if n.startswith("Skin") or n.startswith("Main Body"):
            o.isLightBulbOn = skin_on
        setvis(o.childOccurrences, skin_on)
setvis(root.occurrences, SKIN_ON)
vp = app.activeViewport
cam = vp.camera
cam.isSmoothTransition = False
cam.cameraType = adsk.core.CameraTypes.PerspectiveCameraType
vp.camera = cam
vp.fit()
json.dumps({"doc": app.activeDocument.name})
'''

ORBIT = r'''
import adsk.core, json, math
app = adsk.core.Application.get()
vp = app.activeViewport
cam = vp.camera
t = cam.target
dx, dy, dz = cam.eye.x - t.x, cam.eye.y - t.y, cam.eye.z - t.z
r = math.sqrt(dx*dx + dy*dy) or 1.0
a = math.atan2(dy, dx) + math.radians(DEG)
cam.isSmoothTransition = True
cam.eye = adsk.core.Point3D.create(t.x + r*math.cos(a), t.y + r*math.sin(a), t.z + dz)
cam.upVector = adsk.core.Vector3D.create(0, 0, 1)
vp.camera = cam
adsk.doEvents()
json.dumps({"ok": True})
'''

ZOOM = r'''
import adsk.core, json
app = adsk.core.Application.get()
vp = app.activeViewport
cam = vp.camera
t = cam.target
f = FACTOR
cam.isSmoothTransition = True
cam.eye = adsk.core.Point3D.create(t.x + (cam.eye.x - t.x)*f, t.y + (cam.eye.y - t.y)*f, t.z + (cam.eye.z - t.z)*f)
vp.camera = cam
adsk.doEvents()
json.dumps({"ok": True})
'''


def run(code):
    return fusion._exec("import json\n" + code, 60.0)


def beat(skin_on, orbit_steps=4, deg=18.0, zoom=None, pause=1.4):
    # Fusion animates each camera change itself (isSmoothTransition); a few large moves with a
    # pause long enough for each animation to finish reads as one continuous orbit, while many
    # tiny moves stutter.
    run(SETUP.replace("SKIN_ON", "True" if skin_on else "False"))
    if zoom:
        run(ZOOM.replace("FACTOR", str(zoom)))
    for _ in range(orbit_steps):
        run(ORBIT.replace("DEG", str(deg)))
        time.sleep(pause)


def main(total_s=150):
    t0 = time.time()
    beat(skin_on=True, orbit_steps=5, zoom=0.8)      # assembled jet, slow orbit
    beat(skin_on=False, orbit_steps=6)               # skin off: sourced parts inside
    while time.time() - t0 < total_s:                 # keep it alive until the turn ends
        beat(skin_on=(int(time.time() - t0) // 20) % 2 == 0, orbit_steps=4)
    run(SETUP.replace("SKIN_ON", "True"))
    print(json.dumps({"done": True, "secs": round(time.time() - t0, 1)}))


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 150)
