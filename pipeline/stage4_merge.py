"""
stage4_merge.py -- Stage 4: merge every output/retargeted/<character>_<category>.glb
into ONE file: output/<character>_animations.glb (+ a .json listing, per
category, every animation name inside it).

The merge works directly on the GLB data (no Blender re-import / re-export),
so every animation is copied BYTE-FOR-BYTE and it takes minutes, not hours.
Animations are attached to the base file's skeleton nodes by bone name.

    python run.py --stage merge

Resume-safe: folders whose animations are all in the final file already are
skipped. Before overwriting, the previous final file is kept as
<character>_animations_backup.glb/.json.
"""

import os
import sys
import json
import shutil
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RETARGETED_DIR, character_name, final_glb_path  # noqa: E402


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, _ver, _len = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, f"{path} is not a GLB"
    off = 12
    gltf, binary = None, b""
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            gltf = json.loads(chunk)
        elif ctype == 0x004E4942:
            binary = chunk
        off += 8 + clen
    return gltf, bytearray(binary)


def write_glb(path, gltf, binary):
    js = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    binary = bytes(binary) + b"\x00" * ((4 - len(binary) % 4) % 4)
    gltf_len = 12 + 8 + len(js) + 8 + len(binary)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, gltf_len))
        f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
        f.write(struct.pack("<II", len(binary), 0x004E4942)); f.write(binary)
    os.replace(tmp, path)


def merge_animations(base, bbin, src, sbin, label):
    """Append all of src's animations to base. Returns list of names added."""
    base_nodes = {}
    for i, n in enumerate(base["nodes"]):
        base_nodes.setdefault(n.get("name"), i)

    acc_map, view_map = {}, {}

    def copy_view(vi):
        if vi in view_map:
            return view_map[vi]
        v = dict(src["bufferViews"][vi])
        start = v.get("byteOffset", 0)
        chunk = sbin[start: start + v["byteLength"]]
        while len(bbin) % 4:
            bbin.append(0)
        v["buffer"] = 0
        v["byteOffset"] = len(bbin)
        bbin.extend(chunk)
        base["bufferViews"].append(v)
        view_map[vi] = len(base["bufferViews"]) - 1
        return view_map[vi]

    def copy_acc(ai):
        if ai in acc_map:
            return acc_map[ai]
        a = dict(src["accessors"][ai])
        if "sparse" in a:
            raise RuntimeError(f"{label}: sparse accessors not supported")
        if "bufferView" in a:
            a["bufferView"] = copy_view(a["bufferView"])
        base["accessors"].append(a)
        acc_map[ai] = len(base["accessors"]) - 1
        return acc_map[ai]

    existing = {a.get("name") for a in base.get("animations", [])}
    added = []
    for anim in src.get("animations", []):
        name = anim.get("name")
        if name in existing:
            print(f"  WARNING: '{name}' already in base, skipped")
            continue
        samplers = [
            dict(s, input=copy_acc(s["input"]), output=copy_acc(s["output"]))
            for s in anim["samplers"]
        ]
        channels = []
        for c in anim["channels"]:
            node_name = src["nodes"][c["target"]["node"]].get("name")
            if node_name not in base_nodes:
                raise RuntimeError(f"{label}: bone '{node_name}' not in base file")
            t = dict(c["target"], node=base_nodes[node_name])
            channels.append(dict(c, target=t))
        new = dict(anim, samplers=samplers, channels=channels)
        base.setdefault("animations", []).append(new)
        existing.add(name)
        added.append(name)
    return added


def merge_all():
    out_path = final_glb_path()
    out_json = os.path.splitext(out_path)[0] + ".json"
    prefix = character_name() + "_"
    files = sorted(f for f in os.listdir(RETARGETED_DIR)
                   if f.endswith(".glb") and f.startswith(prefix)) \
        if os.path.isdir(RETARGETED_DIR) else []
    if not files:
        print(f"No {prefix}*.glb files in {RETARGETED_DIR} (run the retarget stage first)")
        return

    manifest = {}
    if os.path.exists(out_path):
        for ext in (".glb", ".json"):
            src = os.path.splitext(out_path)[0] + ext
            if os.path.exists(src):
                shutil.copy2(src, os.path.splitext(out_path)[0] + "_backup" + ext)
        print(f"Backup saved: {os.path.basename(os.path.splitext(out_path)[0])}_backup.glb/.json")
        base_path = out_path
        if os.path.exists(out_json):
            with open(out_json, encoding="utf-8") as f:
                manifest = json.load(f)
    else:
        # first merge: the first per-folder file (character + its animations) is the base
        base_path = os.path.join(RETARGETED_DIR, files[0])
        print(f"No final file yet, starting from {files[0]}")

    print(f"Loading base: {base_path}")
    base, bbin = read_glb(base_path)
    if len(base.get("buffers", [])) != 1:
        raise RuntimeError("base must have exactly one buffer")

    for fname in files:
        folder = fname[len(prefix):-len(".glb")]
        src, sbin = read_glb(os.path.join(RETARGETED_DIR, fname))
        names = [a.get("name") for a in src.get("animations", [])]
        in_base = {a.get("name") for a in base.get("animations", [])}
        if all(n in in_base for n in names):
            manifest[folder] = sorted(set(manifest.get(folder, [])) | set(names))
            print(f"skip {folder}: already in final file")
            continue
        added = merge_animations(base, bbin, src, sbin, fname)
        manifest[folder] = sorted(set(manifest.get(folder, [])) | set(names))
        print(f"merged {folder}: {len(added)} animations | total {len(base['animations'])}")

    base["buffers"][0]["byteLength"] = len(bbin) + (-len(bbin)) % 4
    write_glb(out_path, base, bbin)
    manifest = {k: manifest[k] for k in sorted(manifest)}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"DONE. {len(base['animations'])} animations in {out_path}")


if __name__ == "__main__":
    merge_all()
