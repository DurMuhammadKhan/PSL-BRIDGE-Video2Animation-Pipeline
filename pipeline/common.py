"""
common.py -- shared helpers: where every stage reads and writes its files.

All data lives under OUTPUT_DIR (default: <repo>/output), which is git-ignored:

    output/videos/<category>/          stage 1  PSL .mp4 clips
    output/animations/<category>/      stage 2  Animics .glb animations
    output/retargeted/                 stage 3  <character>_<category>.glb
    output/<character>_animations.glb  stage 4  everything merged into one file
"""
import os
import re
import sys

# Repo root (the folder that holds run.py and config.py). Put it on sys.path so
# every stage can `import config` no matter how it was launched.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config  # noqa: E402


def _abs(path):
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


OUTPUT_DIR = _abs(getattr(config, "OUTPUT_DIR", "output"))
VIDEOS_DIR = os.path.join(OUTPUT_DIR, "videos")
ANIMATIONS_DIR = os.path.join(OUTPUT_DIR, "animations")
RETARGETED_DIR = os.path.join(OUTPUT_DIR, "retargeted")
CHARACTER_DIR = os.path.join(BASE_DIR, "character")

CHARACTER_EXTS = (".glb", ".gltf", ".fbx")


def category_slug(category_url):
    """https://psl.org.pk/dictionary/10-around-the-house -> around-the-house

    Takes the last URL segment and strips the leading "<number>-" id so the
    folder name is human readable.
    """
    last = category_url.rstrip("/").split("/")[-1]     # 10-around-the-house
    slug = re.sub(r"^\d+-", "", last)                  # around-the-house
    return slug or last


def videos_dir_for(category_url):
    """Absolute path to this category's downloaded-videos folder."""
    return os.path.join(VIDEOS_DIR, category_slug(category_url))


def animations_dir_for(category_url):
    """Absolute path to this category's exported-animations folder."""
    return os.path.join(ANIMATIONS_DIR, category_slug(category_url))


def character_path():
    """The rigged character to retarget onto.

    config.CHARACTER_FILE if set, otherwise the single model file found in
    character/. Raises a clear error if there is none (or more than one).
    """
    explicit = getattr(config, "CHARACTER_FILE", None)
    if explicit:
        path = _abs(explicit)
        if not os.path.exists(path):
            raise FileNotFoundError(f"config.CHARACTER_FILE not found: {path}")
        return path
    found = sorted(
        f for f in os.listdir(CHARACTER_DIR)
        if os.path.splitext(f)[1].lower() in CHARACTER_EXTS
    ) if os.path.isdir(CHARACTER_DIR) else []
    if not found:
        raise FileNotFoundError(
            f"No character model in {CHARACTER_DIR}. Put your rigged character "
            f"(.glb/.gltf/.fbx) there, or set CHARACTER_FILE in config.py.")
    if len(found) > 1:
        raise RuntimeError(
            f"More than one model in {CHARACTER_DIR}: {found}. Keep one, or set "
            f"CHARACTER_FILE in config.py.")
    return os.path.join(CHARACTER_DIR, found[0])


def character_name():
    """'character/Ali.glb' -> 'Ali'. Used to name every stage 3/4 output."""
    return os.path.splitext(os.path.basename(character_path()))[0]


def final_glb_path():
    """Stage 4 output: output/<character>_animations.glb"""
    return os.path.join(OUTPUT_DIR, f"{character_name()}_animations.glb")
