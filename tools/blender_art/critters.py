"""Halloween crawlies, rendered in Blender (dev-only - tools/ never ships).

Runs INSIDE Blender, headless:

    blender.exe -b --factory-startup -P tools/blender_art/critters.py -- \
        spider walk OUT_DIR [--size 256] [--frames 16] [--only 3] [--fur]

Every bug is built from code, seen from straight above by an orthographic
camera, on a transparent film with a shadow-catcher floor - so each frame is
a PNG of the bug plus its own soft contact shadow, ready to be dropped over
the app. The app plays the frames as a flipbook and turns the sprite to face
its heading.

The light sits almost overhead ON PURPOSE. The sprite is rotated at runtime,
so any strongly sideways light would swing round with the bug; near-overhead
light gives real 3D form (lit backs, dark undersides, arched legs casting
shadows) that still looks right at every heading.

WALK LOOP CONTRACT (the app depends on it): a loop is one full gait cycle.
Each foot is planted for half the cycle, and while planted it slides back
under the body by exactly STRIDE units. So one loop == 2 * STRIDE units of
travel. Play frames by DISTANCE travelled, not by time, and no foot skates.
The .json written next to the frames carries the numbers.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


# -- scene -----------------------------------------------------------------
def reset_scene(size: int, view: float, samples: int):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "Standard"     # AgX greys the browns out
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.75, 0.78, 0.9, 1)
    bg.inputs[1].default_value = 0.30
    sc.world = world

    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = view
    cam = bpy.data.objects.new("cam", cam_d)
    cam.location = (0, 0, 20)
    sc.collection.objects.link(cam)
    sc.camera = cam

    key_d = bpy.data.lights.new("key", "AREA")
    key_d.shape = "DISK"                   # a square lamp leaves square glints
    key_d.energy = 1500
    key_d.size = 9
    key = bpy.data.objects.new("key", key_d)
    key.location = (1.6, 1.8, 10)          # a touch ahead-left of the bug
    key.rotation_euler = (-0.17, 0.15, 0)
    sc.collection.objects.link(key)
    return sc


def shadow_floor():
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    floor = bpy.context.object
    floor.is_shadow_catcher = True
    return floor


def material(name, color, rough=0.45, sheen=0.0, coat=0.0, bump=0.0,
             mottle=None, scale=9.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    for key, val in (("Sheen Weight", sheen), ("Coat Weight", coat)):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = val
    if "Sheen Roughness" in bsdf.inputs:
        bsdf.inputs["Sheen Roughness"].default_value = 0.35
    if mottle or bump:
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 6
        if mottle:
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].position = 0.35
            ramp.color_ramp.elements[0].color = (*color, 1)
            ramp.color_ramp.elements[1].position = 0.75
            ramp.color_ramp.elements[1].color = (*mottle, 1)
            nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        if bump:
            b = nt.nodes.new("ShaderNodeBump")
            b.inputs["Strength"].default_value = bump
            nt.links.new(noise.outputs["Fac"], b.inputs["Height"])
            nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def ellipsoid(name, loc, radii, mat, segs=48):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2,
                                         radius=1, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = radii
    bpy.ops.object.shade_smooth()
    ob.data.materials.append(mat)
    return ob


def tube(name, points, radii, mat):
    """A jointed limb: straight tapered segments through `points`."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 1.0
    cu.bevel_resolution = 5
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for pt, p, r in zip(sp.points, points, radii):
        pt.co = (p[0], p[1], p[2], 1)
        pt.radius = r
    ob = bpy.data.objects.new(name, cu)
    ob.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def fur(ob, count, length, seed=1):
    mod = ob.modifiers.new("fur", "PARTICLE_SYSTEM")
    ps = mod.particle_system.settings
    ps.type = "HAIR"
    ps.count = count
    ps.hair_length = length
    ps.child_type = "INTERPOLATED"
    ps.rendered_child_count = 12
    ps.material = 2                     # slot 2 = the hair material
    mod.particle_system.seed = seed
    return mod


# -- spider ----------------------------------------------------------------
STRIDE = 1.15
SPIDER_VIEW = 9.2           # world units across the square frame
# (hip, rest foot, gait group) for one side; the other side is mirrored
SPIDER_LEGS = [((0.95, 0.42), (3.05, 1.45), 0),
               ((0.70, 0.58), (1.65, 3.05), 1),
               ((0.42, 0.58), (-0.45, 3.25), 0),
               ((0.12, 0.46), (-2.65, 2.05), 1)]
HIP_Z = 0.62
LEG_SLACK = 1.30            # bone length vs rest reach: > 1 keeps the knee up


def leg_points(hip, foot, total, sweep, knee_bias=0.44):
    """Jointed leg, knee UP and swept `sweep` radians toward the head (+) or
    the tail (-). The sweep matters more than it sounds: seen from straight
    above, a knee that only bends upward is invisible and the leg reads as a
    straight stick. Real legs kink in plan view too. `total` is the fixed bone
    length, so the leg never stretches."""
    hip, foot = Vector(hip), Vector(foot)
    flat = Vector((foot.x - hip.x, foot.y - hip.y, 0))
    reach = flat.length
    out = flat.normalized()
    side = Vector((0, 0, 1)).cross(out)             # horizontal, across the leg
    if side.x < 0:
        side = -side                                # now it points headward
    up = Vector((0, 0, 1)) * math.cos(sweep) + side * math.sin(sweep)
    a, b = total * knee_bias, total * (1 - knee_bias)
    d = max(abs(a - b) + 1e-3, min(a + b - 1e-3, (foot - hip).length))
    elev = math.atan2(foot.z - hip.z, reach)
    bend = math.acos(max(-1, min(1, (a * a + d * d - b * b) / (2 * a * d))))
    ang = elev + bend
    knee = hip + out * (a * math.cos(ang)) + up * (a * math.sin(ang))
    # the shin is two pieces: it drops steeply, then the foot splays a little
    ankle = knee.lerp(foot, 0.60) + up * (0.12 * total)
    return hip, knee, ankle, foot


def foot_at(rest, phase, lift=0.55):
    """Body-frame foot position at `phase` of the gait cycle (0..1)."""
    if phase < 0.5:                                   # planted, sliding back
        return (rest[0] + STRIDE * (0.5 - 2 * phase), rest[1], 0.0)
    u = (phase - 0.5) * 2                             # in the air, reaching
    e = u * u * (3 - 2 * u)
    return (rest[0] - STRIDE * 0.5 + STRIDE * e, rest[1],
            lift * math.sin(math.pi * u))


def build_spider(phase: float, hang: bool, use_fur: bool):
    # A dark tarantula with rust knees: near-black reads as a real spider, and
    # the rust bands are what keep it visible on the app's dark purple.
    body = material("body", (0.018, 0.011, 0.008), rough=0.7, sheen=0.25,
                    bump=0.5, mottle=(0.12, 0.035, 0.012), scale=6.0)
    shell = material("shell", (0.030, 0.017, 0.010), rough=0.42, sheen=0.15,
                     coat=0.15, bump=0.25, mottle=(0.16, 0.07, 0.03),
                     scale=4.0)
    legm = material("leg", (0.016, 0.010, 0.008), rough=0.6, sheen=0.3,
                    bump=0.6, scale=5.0)
    kneem = material("knee", (0.55, 0.16, 0.03), rough=0.55, sheen=0.4,
                     bump=0.5, mottle=(0.80, 0.34, 0.08), scale=8.0)
    eye = material("eye", (0.004, 0.004, 0.004), rough=0.05, coat=1.0)
    hairm = material("hair", (0.20, 0.06, 0.02), rough=0.7, sheen=0.3)

    bob = 0.035 * math.sin(phase * 4 * math.pi)
    abd = ellipsoid("abdomen", (-1.22, 0, 0.92 + bob), (1.28, 1.0, 0.86), body)
    ellipsoid("ceph", (0.62, 0, 0.66 + bob), (0.92, 0.76, 0.46), shell)
    ellipsoid("waist", (-0.12, 0, 0.66 + bob), (0.30, 0.30, 0.26), shell, 24)
    for side in (1, -1):
        ellipsoid("jaw", (1.42, 0.17 * side, 0.50 + bob), (0.24, 0.15, 0.20),
                  shell, 24)
        # pedipalps: the two short "arms" by the mouth
        tube("palp", [(1.30, 0.34 * side, 0.55 + bob),
                      (1.78, 0.52 * side, 0.62 + bob),
                      (2.08, 0.40 * side, 0.22)],
             [0.13, 0.11, 0.07], legm)
    for ex, ey, r in ((1.30, 0.13, 0.085), (1.18, 0.34, 0.06)):
        for side in (1, -1):
            ellipsoid("eye", (ex, ey * side, 0.98 + bob), (r, r, r), eye, 16)
    if use_fur:
        abd.data.materials.append(hairm)
        fur(abd, 1400, 0.26, seed=3)

    for i, (hip, rest, group) in enumerate(SPIDER_LEGS):
        total = math.hypot(rest[0] - hip[0], rest[1] - hip[1]) * LEG_SLACK
        for side in (1, -1):
            g = group if side > 0 else 1 - group
            ph = (phase + 0.5 * g + 0.04 * i) % 1.0
            h = (hip[0], hip[1] * side, HIP_Z + bob)
            if hang:
                curl = 0.58 + 0.05 * math.sin(phase * 2 * math.pi
                                              + i * 1.3 + side)
                f = (rest[0] * curl, rest[1] * side * curl, -0.25)
            else:
                fx, fy, fz = foot_at(rest, ph)
                f = (fx, fy * side, fz)
            sweep = (0.95, 0.75, -0.75, -0.95)[i]
            pts = leg_points(h, f, total, sweep)
            tube("leg", [tuple(p) for p in pts], [0.19, 0.15, 0.10, 0.035],
                 legm)
            # the rust knee: a short sleeve over the joint
            k = pts[1]
            tube("knee", [tuple(k.lerp(pts[0], 0.20)), tuple(k),
                          tuple(k.lerp(pts[2], 0.30))],
                 [0.175, 0.172, 0.145], kneem)
            a = pts[2]
            tube("ankle", [tuple(a.lerp(pts[1], 0.12)), tuple(a),
                           tuple(a.lerp(pts[3], 0.12))],
                 [0.118, 0.112, 0.095], kneem)


BUGS = {"spider": (build_spider, SPIDER_VIEW)}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    kind, clip, out = argv[0], argv[1], Path(argv[2])
    opt = argv[3:]

    def val(flag, default):
        return type(default)(opt[opt.index(flag) + 1]) if flag in opt else default

    size, frames = val("--size", 256), val("--frames", 16)
    samples, only = val("--samples", 48), val("--only", -1)
    build, view = BUGS[kind]
    out.mkdir(parents=True, exist_ok=True)
    for f in range(frames):
        if only >= 0 and f != only:
            continue
        sc = reset_scene(size, view, samples)
        if clip != "hang":
            shadow_floor()
        build(f / frames, clip == "hang", "--fur" in opt)
        sc.render.filepath = str(out / f"{kind}_{clip}_{f:02d}.png")
        bpy.ops.render.render(write_still=True)
    (out / f"{kind}_{clip}.json").write_text(json.dumps({
        "kind": kind, "clip": clip, "frames": frames, "size": size,
        "view_units": view, "stride_units": STRIDE,
        "px_per_unit": size / view,
        "loop_travel_px": 2 * STRIDE * size / view,
    }, indent=2))
    print("CRITTERS_OK", kind, clip)


main()
