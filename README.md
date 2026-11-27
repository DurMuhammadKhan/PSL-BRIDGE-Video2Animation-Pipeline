# PSL Video to Animation

Turn Pakistan Sign Language (PSL) dictionary videos into 3D animations on
**your own rigged character** — end to end, in one command, or one stage at a
time.

| Stage | What it does | Output |
|---|---|---|
| 1. `download` | Scrapes sign clips from [psl.org.pk](https://psl.org.pk) | `output/videos/<category>/*.mp4` |
| 2. `animate` | Drives [Animics](https://animics.gti.upf.edu/) (MediaPipe pose extraction) and exports one `.glb` animation per clip | `output/animations/<category>/*.glb` |
| 3. `retarget` | In Blender, puts every animation onto your character | `output/retargeted/<character>_<category>.glb` |
| 4. `merge` | Combines everything into one file | `output/<character>_animations.glb` |

Every stage is **resume-safe**: anything already done is skipped, so after a
stop or crash just run the same command again.

## Folder layout

```
PSL-Video-to-Animation/
├── run.py              <- runs all stages, or one with --stage
├── config.py           <- the only file you normally edit
├── check_animics.py    <- "is the Animics server healthy right now?"
├── requirements.txt
├── pipeline/
│   ├── common.py            shared paths / naming
│   ├── stage1_download.py
│   ├── stage2_animate.py
│   ├── stage3_retarget.py   (runs inside Blender)
│   └── stage4_merge.py
├── character/          <- put YOUR rigged character here
├── viewer/viewer.html  <- preview the final file in a browser
└── output/             <- everything generated (not in git)
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

You also need:
- **Google Chrome** (stages 1–2). Selenium downloads the matching chromedriver itself.
- **[Blender](https://www.blender.org/download/)** (stage 3). It is found
  automatically at `/Applications/Blender.app` on Mac or as `blender` on your
  PATH; otherwise set `BLENDER_PATH` in `config.py`.

## Add your character

1. Put **one** rigged character file in `character/` — `.glb`, `.gltf` or `.fbx`,
   with a skeleton (armature). For example `character/Ali.glb`.
2. Its name is used for every output: `output/retargeted/Ali_<category>.glb`
   and `output/Ali_animations.glb`.
3. Map the bones. Animics animations use Mixamo-style bone names (`Hips`,
   `Spine`, `LeftArm`, `LeftForeArm`, `LeftHand`, ...). In `config.py`:

   ```python
   BONE_NAME_MAP = {
       # your character's bone : Animics bone
       "pelvis":     "Hips",
       "upperarm_l": "LeftArm",
       ...
   }
   ```

   - If your character already uses Mixamo names (with or without a
     `mixamorig:` prefix), you don't need to change anything.
   - With `AUTO_MATCH_UNMAPPED = True`, bones you didn't list are matched by
     name automatically.
   - Stage 3 prints an **AUTO-MATCH REPORT** listing your bones it could not
     match. Add those to `BONE_NAME_MAP` and run stage 3 again. Tip: open a
     file from `output/animations/` and your character in Blender and compare
     the bone names in the Outliner.
4. Optional: `BAKE_FRAME_START` / `BAKE_FRAME_END` choose which frames of each
   animation are baked (default: from frame 5 to the end).

Using a different character later? Swap the file in `character/` and run
stages 3–4 again — it gets its own `<name>_*.glb` files.

## Choose categories

In `config.py`, `None` = whole category, a list = only those words:

```python
CATEGORIES = {
    "https://psl.org.pk/dictionary/10-around-the-house": None,
    "https://psl.org.pk/dictionary/58-numbers": ["One", "two", "fifteen"],
}
```

## Run

```bash
python run.py                       # all four stages

python run.py --stage download      # one stage at a time
python run.py --stage animate
python run.py --stage retarget
python run.py --stage merge

python run.py --stage retarget --category verbs   # one folder only
```

Animics is a shared research server and is sometimes overloaded. Check it
before a big stage-2 run:

```bash
python check_animics.py && python run.py --stage animate
```

Stage 3 also picks up any extra folders you drop into `output/animations/`
by hand (each subfolder = one category).

## Trim

In stage 2 each clip is trimmed in time before pose extraction (default: the
first 50%). In `config.py`:

```python
TRIM_START_RATIO = 0.0   # first 50%: 0.0 -> 0.5
TRIM_END_RATIO   = 0.5   # last 50%: 0.5 -> 1.0 | middle 50%: 0.25 -> 0.75
```

## Preview the result

```bash
python -m http.server 8000
```

Then open
`http://localhost:8000/viewer/viewer.html?file=../output/<character>_animations.glb`
and click an animation name.

## Notes

- Stage 2 is most reliable with a visible browser on a machine with a GPU
  (`HEADLESS_ANIMICS = False`). On a headless server use a virtual display
  (`xvfb-run python run.py --stage animate`).
- Stage 2 drives Animics' internal JavaScript directly; it can break if Animics
  renames those internals.
- A `trackCount: 0` warning means a clip exported without motion — re-check it.
- Stage 3 runs one fresh Blender process per category to keep memory low.
