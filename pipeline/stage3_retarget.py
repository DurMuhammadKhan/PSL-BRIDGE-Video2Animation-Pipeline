"""
stage3_retarget.py -- Stage 3: put every Animics animation onto YOUR character.

For each folder output/animations/<category>/ it loads your rigged character
(the model in character/), retargets every animation onto it in Blender, and
writes output/retargeted/<character>_<category>.glb (character + that folder's
animations, each as an action named "<category>_<filename>").

Run it through the pipeline (it finds Blender and runs one fresh Blender
process per folder, which keeps memory low and speed steady):

    python run.py --stage retarget
    python run.py --stage retarget --category verbs   # just one folder

Resume-safe: animations already in a per-folder file or in the final
<character>_animations.glb are skipped. Bone names / frame range settings are
in config.py (BONE_NAME_MAP, AUTO_MATCH_UNMAPPED, BAKE_FRAME_START/END).
"""

import os
import sys
import math
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (ANIMATIONS_DIR, RETARGETED_DIR, character_path,  # noqa: E402
                    character_name, final_glb_path)
import config  # noqa: E402

try:  # only available inside Blender (or with the `bpy` pip module)
    import bpy
    from mathutils import Vector, Quaternion  # noqa: F401
    HAVE_BPY = True
except ImportError:
    HAVE_BPY = False

# ============================================================
# Settings (from config.py)
# ============================================================

DATA_DIR = ANIMATIONS_DIR
PER_FOLDER_DIR = RETARGETED_DIR
BONE_NAME_MAP = config.BONE_NAME_MAP
AUTO_MATCH_UNMAPPED = config.AUTO_MATCH_UNMAPPED
BAKE_FRAME_START = config.BAKE_FRAME_START
BAKE_FRAME_END = config.BAKE_FRAME_END
FORCE_REPROCESS = set(getattr(config, "FORCE_REPROCESS", ()))


# ============================================================
# Helpers
# ============================================================

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_glb(filepath):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=filepath)
    after = set(bpy.data.objects)
    return list(after - before)


def import_bvh(filepath):
    before = set(bpy.data.objects)
    bpy.ops.import_anim.bvh(
        filepath=filepath,
        axis_forward="-Z",
        axis_up="Y",
        rotate_mode="NATIVE",
    )
    after = set(bpy.data.objects)
    return list(after - before)


def find_armature(objects):
    for obj in objects:
        if obj.type == "ARMATURE":
            return obj
    return None


def normalize(name):
    lowered = name.lower()
    for prefix in ("mixamorig:", "mixamorig_", "mixamorig"):
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix):]
            break
    return lowered.replace("_", "").replace(" ", "").replace(".", "").replace(":", "")


def build_bone_mapping(char_arm, src_arm):
    """Return dict: char_bone_name -> src_bone_name"""
    src_names = [b.name for b in src_arm.pose.bones]
    src_norm = {normalize(n): n for n in src_names}

    mapping = {}
    unmatched = []

    for char_bone_name in [b.name for b in char_arm.pose.bones]:
        explicit = BONE_NAME_MAP.get(char_bone_name)
        if explicit and explicit in src_names:
            mapping[char_bone_name] = explicit
            continue
        # explicit name didn't match this rig's naming (e.g. it uses a
        # 'mixamorig_' prefix) -> fall through to auto-match silently; only
        # a genuinely unmatched bone is reported below.

        if not AUTO_MATCH_UNMAPPED:
            continue

        norm = normalize(char_bone_name)
        if norm in src_norm:
            mapping[char_bone_name] = src_norm[norm]
            continue

        # "contains" fallback e.g. mixamorig:LeftArm vs LeftArm
        candidates = [n for n in src_names if norm in normalize(n) or normalize(n) in norm]
        if len(candidates) == 1:
            mapping[char_bone_name] = candidates[0]
        else:
            unmatched.append(char_bone_name)

    print("\n=== AUTO-MATCH REPORT ===")
    print(f"Character bones matched: {len(mapping)} / {len(char_arm.pose.bones)}")
    if unmatched:
        print("Unmatched character bones (add these to BONE_NAME_MAP):")
        for n in unmatched:
            print(f"  '{n}': None,")
    print("=========================\n")

    return mapping


def get_action_frame_range(action):
    return action.frame_range[0], action.frame_range[1]


def rest_local_quat(bone):
    """Bone's rest orientation relative to its OWN parent (constant, bind pose)."""
    if bone.parent is None:
        return bone.matrix_local.to_quaternion()
    return (bone.parent.matrix_local.inverted() @ bone.matrix_local).to_quaternion()


def rest_armature_quat(bone):
    """Bone's rest orientation in its OWN armature/object space (constant)."""
    return bone.matrix_local.to_quaternion()


def topo_order(arm, names):
    """names ordered so a bone's parent always comes before it."""
    name_set = set(names)
    order = []
    visited = set()

    def visit(n):
        if n in visited:
            return
        bone = arm.data.bones[n]
        if bone.parent is not None and bone.parent.name in name_set:
            visit(bone.parent.name)
        visited.add(n)
        order.append(n)

    for n in names:
        visit(n)
    return order


def retarget_bake(char_arm, src_arm, mapping, frame_start, frame_end, action_name):
    """
    Per-frame direct keyframing with a rest-difference conjugation per bone,
    solved in ARMATURE (object) space and converted back to each bone's own
    local rotation channel via its parent's already-computed current
    orientation.

    Why not a naive rotation copy (local- or world-space, tried first): a
    bone's rest orientation relative to its own PARENT is not the same
    convention between this Mixamo-style animation rig and the character rig
    for several bones (not just hands - even the upper arm bones differ by
    ~80 deg parent-relative, because the parent/shoulder chains themselves
    are rigged differently) - local-space copy breaks immediately, and
    world-space copy still discards each bone's own axis-roll convention,
    which showed up as twisted/contorted fingers.

    Correct fix (matches the local-quaternion engine already proven in the
    PSL pipeline's Animation2 rewrite): for each bone, in ARMATURE space,
        A = char_rest_armature^-1 @ src_rest_armature      (fixed per bone)
        src_delta  = src_rest_armature^-1 @ src_current_armature
        tgt_delta  = A @ src_delta @ A.inverted()
        tgt_armature_current = char_rest_armature @ tgt_delta
    then converted into the character bone's own LOCAL rotation channel via
    the standard FK relation (bones processed parent-before-child so the
    parent's just-computed current armature orientation is available):
        matrix_basis = rest_local^-1 @ parent_current_armature^-1 @ tgt_armature_current
    """
    for src_name in mapping.values():
        src_arm.pose.bones[src_name].rotation_mode = "QUATERNION"
    for char_name in mapping:
        char_arm.pose.bones[char_name].rotation_mode = "QUATERNION"

    order = topo_order(char_arm, list(mapping.keys()))

    rest_char_arm = {}
    rest_src_arm = {}
    rest_char_local = {}
    offset = {}
    root_bone_name = None

    for char_name in order:
        src_name = mapping[char_name]
        char_bone = char_arm.data.bones[char_name]
        src_bone = src_arm.data.bones[src_name]
        rest_char_arm[char_name] = rest_armature_quat(char_bone)
        rest_src_arm[char_name] = rest_armature_quat(src_bone)
        rest_char_local[char_name] = rest_local_quat(char_bone)
        offset[char_name] = rest_char_arm[char_name].inverted() @ rest_src_arm[char_name]
        if char_bone.parent is None:
            root_bone_name = char_name

    if char_arm.animation_data is None:
        char_arm.animation_data_create()
    new_action = bpy.data.actions.new(action_name)
    new_action.use_fake_user = True  # keep it alive once it stops being the active action
    char_arm.animation_data.action = new_action

    scene = bpy.context.scene
    fs, fe = int(frame_start), int(math.ceil(frame_end))
    for f in range(fs, fe + 1):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        src_arm_eval = src_arm.evaluated_get(dg)

        char_current_arm = {}
        for char_name in order:
            src_name = mapping[char_name]
            src_pbone_eval = src_arm_eval.pose.bones[src_name]
            src_current_arm = src_pbone_eval.matrix.to_quaternion()

            src_delta = rest_src_arm[char_name].inverted() @ src_current_arm
            A = offset[char_name]
            tgt_delta = A @ src_delta @ A.inverted()
            tgt_current_arm = rest_char_arm[char_name] @ tgt_delta
            char_current_arm[char_name] = tgt_current_arm

            char_bone = char_arm.data.bones[char_name]
            if char_bone.parent is not None and char_bone.parent.name in char_current_arm:
                parent_current_arm = char_current_arm[char_bone.parent.name]
            else:
                parent_current_arm = Quaternion((1.0, 0.0, 0.0, 0.0))

            matrix_basis_rot = (
                rest_char_local[char_name].inverted()
                @ parent_current_arm.inverted()
                @ tgt_current_arm
            )

            char_pbone = char_arm.pose.bones[char_name]
            char_pbone.rotation_quaternion = matrix_basis_rot
            char_pbone.keyframe_insert(data_path="rotation_quaternion", frame=f - fs)

        if root_bone_name:
            src_root_eval = src_arm_eval.pose.bones[mapping[root_bone_name]]
            char_root = char_arm.pose.bones[root_bone_name]
            char_root.location = src_root_eval.location
            char_root.keyframe_insert(data_path="location", frame=f - fs)

    return new_action


def cleanup_source(src_arm_obj, src_objects):
    src_action = None
    if src_arm_obj.animation_data and src_arm_obj.animation_data.action:
        src_action = src_arm_obj.animation_data.action

    for obj in src_objects:
        bpy.data.objects.remove(obj, do_unlink=True)

    if src_action is not None:
        bpy.data.actions.remove(src_action, do_unlink=True)

    # drop any other orphaned data (meshes, images, etc.) left over from the
    # deleted source armature so the export contains only the character's data
    bpy.data.orphans_purge(do_local_ids=True)


def export_glb(filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format="GLB",
        export_animations=True,
        export_animation_mode="ACTIONS",   # export every action still in the file (each retargeted clip)
        # We already bake an explicit keyframe on EVERY frame during retargeting,
        # so force-sampling (which re-evaluates the whole scene frame-by-frame for
        # every action) is pure wasted work and was the real export bottleneck.
        # Reading the existing dense keyframes directly is dramatically faster and
        # produces identical animation.
        export_force_sampling=False,
        export_nla_strips=False,
        # No modifiers matter for the armature/mesh here; skipping the apply step
        # avoids re-evaluating meshes on every checkpoint export.
        export_apply=False,
    )


# ============================================================
# Main
# ============================================================

def _collapse_spaces(s):
    """Collapse any run of whitespace to a single space and trim ends."""
    return " ".join(s.split())


def clean_category(category):
    """Folder -> clean label: drop a trailing '_animations' suffix, turn
    hyphens into spaces, collapse extra spaces."""
    if category.endswith("_animations"):
        category = category[:-len("_animations")]
    category = category.replace("-", " ")
    return _collapse_spaces(category)


def clean_filename(name):
    """GLB file name -> clean label: turn '_' and '-' into spaces, collapse
    extra spaces. Other characters (spaces, brackets, dots) are kept as-is."""
    name = name.replace("_", " ").replace("-", " ")
    return _collapse_spaces(name)


def discover_animation_files(data_dir):
    """Yield (filepath, action_name) for every animation file under
    data_dir/<category>/<name>.<glb|gltf|bvh>.
    action_name = "<clean_category>_<clean_filename>" where the category has
    any '_animations' suffix removed and '-' -> space, and the file name has
    '_'/'-' -> space (see clean_category / clean_filename)."""
    entries = []
    for category in sorted(os.listdir(data_dir)):
        cat_path = os.path.join(data_dir, category)
        if not os.path.isdir(cat_path):
            continue
        cat_label = clean_category(category)
        for fname in sorted(os.listdir(cat_path)):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in (".glb", ".gltf", ".bvh"):
                continue
            name = clean_filename(os.path.splitext(fname)[0])
            action_name = f"{cat_label}_{name}"
            # Blender caps ID names at 63 bytes; use the same name it stores
            action_name = action_name.encode("utf-8")[:63].decode("utf-8", "ignore")
            entries.append((os.path.join(cat_path, fname), action_name))
    return entries


def process_one_animation(char_arm, filepath, action_name):
    print(f"\n--- {action_name}  <-  {filepath} ---")
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".glb", ".gltf"):
        anim_objects = import_glb(filepath)
    elif ext == ".bvh":
        anim_objects = import_bvh(filepath)
    else:
        print(f"WARNING: unsupported file type '{ext}', skipping")
        return

    src_arm = find_armature(anim_objects)
    if src_arm is None:
        print("WARNING: no armature found in this file, skipping")
        for o in anim_objects:
            bpy.data.objects.remove(o, do_unlink=True)
        return

    if not (src_arm.animation_data and src_arm.animation_data.action):
        print("WARNING: no action/keyframes found in this file, skipping")
        cleanup_source(src_arm, anim_objects)
        return

    f_start, f_end = get_action_frame_range(src_arm.animation_data.action)
    if BAKE_FRAME_START is not None:
        f_start = BAKE_FRAME_START
    if BAKE_FRAME_END is not None:
        f_end = BAKE_FRAME_END
    print(f"Baking frame range: {f_start} - {f_end}")

    mapping = build_bone_mapping(char_arm, src_arm)
    if not mapping:
        print("WARNING: no bones could be matched, skipping "
              "(fill in BONE_NAME_MAP manually if this keeps happening)")
        cleanup_source(src_arm, anim_objects)
        return

    retarget_bake(char_arm, src_arm, mapping, f_start, f_end, action_name)
    cleanup_source(src_arm, anim_objects)


def load_existing_output(output_path):
    """If this output .glb already exists, load its character + all its previously
    baked actions (so they're kept, not recomputed). Returns (char_arm,
    already_done_names) or (None, set()) if there's nothing to resume from."""
    if not os.path.exists(output_path):
        return None, set()

    print(f"Found existing output, resuming from: {output_path}")
    objects = import_glb(output_path)
    char_arm = find_armature(objects)
    if char_arm is None:
        print("WARNING: existing output has no armature, starting fresh")
        for o in objects:
            bpy.data.objects.remove(o, do_unlink=True)
        return None, set()

    already_done = set()
    for act in bpy.data.actions:
        act.use_fake_user = True  # keep it alive once it stops being the active action
        already_done.add(act.name)
    return char_arm, already_done


def write_manifest_json(entries, json_path):
    """Write a sidecar JSON listing, per source folder, the action names that
    actually made it into the output .glb. Shape:
        {
          "English-Alphabets": ["English Alphabets_a", "English Alphabets_b", ...],
          "Numbers": ["Numbers_10", "Numbers_20", ...],
          ...
        }
    Only actions currently present in the exported file are listed."""
    present = {a.name for a in bpy.data.actions}
    grouped = {}
    for filepath, action_name in entries:
        if action_name not in present:
            continue
        folder = os.path.basename(os.path.dirname(filepath))
        grouped.setdefault(folder, [])
        if action_name not in grouped[folder]:
            grouped[folder].append(action_name)

    # any action in the file we couldn't trace back to a current data/ folder
    traced = {n for names in grouped.values() for n in names}
    orphan = sorted(present - traced)
    if orphan:
        grouped["(no source folder)"] = orphan

    for k in grouped:
        grouped[k].sort()
    ordered = {k: grouped[k] for k in sorted(grouped)}

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(ordered, f, indent=2, ensure_ascii=False)
    total = sum(len(v) for v in ordered.values())
    print(f"Wrote manifest ({len(ordered)} folders, {total} animations): {json_path}")


def parse_only_category():
    """Value of --only-category (works with Blender's `-- --only-category X`)."""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if "--only-category" in argv:
        i = argv.index("--only-category")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def per_folder_glb(category):
    return os.path.join(PER_FOLDER_DIR, f"{character_name()}_{category}.glb")


def done_action_names():
    """Lower-cased names of every action already retargeted: those listed in the
    final <character>_animations.json and in every per-folder .json. Compared
    case-insensitively so e.g. 'Numbers_10' and 'numbers_10' count as the same."""
    jsons = [os.path.splitext(final_glb_path())[0] + ".json"]
    if os.path.isdir(PER_FOLDER_DIR):
        jsons += [os.path.join(PER_FOLDER_DIR, f) for f in os.listdir(PER_FOLDER_DIR)
                  if f.endswith(".json")]
    done = set()
    for path in jsons:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for names in json.load(fh).values():
                    done.update(n.lower() for n in names)
    return done


def import_character(path):
    if path.lower().endswith(".fbx"):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=path)
        return list(set(bpy.data.objects) - before)
    return import_glb(path)


def bake_one_folder(category):
    """Runs INSIDE Blender: retarget output/animations/<category>/ onto the
    character and save output/retargeted/<character>_<category>.glb (+ .json)."""
    reset_scene()
    out_glb = per_folder_glb(category)
    print(f"Per-folder output: {out_glb}")

    char_arm, already_done = load_existing_output(out_glb)
    if char_arm is None:
        print(f"Importing character: {character_path()}")
        char_arm = find_armature(import_character(character_path()))
        if char_arm is None:
            raise RuntimeError("No armature (skeleton) found in the character file")
    already_lower = {n.lower() for n in already_done} | done_action_names()

    entries = [e for e in discover_animation_files(DATA_DIR)
               if os.path.basename(os.path.dirname(e[0])) == category]
    to_process = [(fp, name) for fp, name in entries
                  if name.lower() not in already_lower or name in FORCE_REPROCESS]
    print(f"{len(entries)} file(s) in '{category}': "
          f"{len(entries) - len(to_process)} already done, {len(to_process)} to process")
    if not to_process:
        print("Nothing new to process.")
        return

    for n, (filepath, action_name) in enumerate(to_process, 1):
        stale = bpy.data.actions.get(action_name)
        if stale is not None:  # FORCE_REPROCESS: drop the old version first
            bpy.data.actions.remove(stale, do_unlink=True)
        process_one_animation(char_arm, filepath, action_name)
        print(f"[{n}/{len(to_process)}]")

    export_glb(out_glb)
    write_manifest_json(entries, os.path.splitext(out_glb)[0] + ".json")
    print(f"Saved '{category}': {len(bpy.data.actions)} action(s) in {out_glb}")


# ============================================================
# Outside Blender: launch one Blender process per folder
# ============================================================

def find_blender():
    """config.BLENDER_PATH, else the usual install locations, else `blender`."""
    import shutil
    candidates = [getattr(config, "BLENDER_PATH", None),
                  "/Applications/Blender.app/Contents/MacOS/Blender",
                  shutil.which("blender")]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError("Blender not found. Install Blender, or set "
                            "BLENDER_PATH in config.py to its executable.")


def retarget_all(only=None):
    """Retarget every folder that still has animations not yet on the character.
    only = a category name to limit the run to that one folder."""
    if not os.path.isdir(DATA_DIR):
        print(f"No animations folder yet: {DATA_DIR} (run the animate stage first)")
        return True
    print(f"Character: {character_path()}")
    done = done_action_names()
    todo = []
    for fp, name in discover_animation_files(DATA_DIR):
        cat = os.path.basename(os.path.dirname(fp))
        if (only is None or cat == only) and name.lower() not in done and cat not in todo:
            todo.append(cat)
    if not todo:
        print("Every animation is already retargeted - nothing to do.")
        return True

    me = os.path.abspath(__file__)
    if HAVE_BPY:   # this python can import bpy itself
        base_cmd = [sys.executable, me]
    else:
        # --python-exit-code 1: make Blender exit non-zero if the script raises
        base_cmd = [find_blender(), "--background", "--python-exit-code", "1",
                    "--python", me, "--"]

    print(f"{len(todo)} folder(s) to retarget (one fresh Blender process each).")
    for i, cat in enumerate(todo, 1):
        print(f"\n#####  [{i}/{len(todo)}]  FOLDER: {cat}  #####", flush=True)
        result = subprocess.run(base_cmd + ["--only-category", cat])
        if result.returncode != 0:
            print(f"\n!! Folder '{cat}' failed (exit {result.returncode}). Finished "
                  f"folders are saved; run the retarget stage again to resume.")
            return False
    return True


if __name__ == "__main__":
    category = parse_only_category()
    if HAVE_BPY and category:
        bake_one_folder(category)        # we are the per-folder Blender process
    else:
        sys.exit(0 if retarget_all(only=category) else 1)
