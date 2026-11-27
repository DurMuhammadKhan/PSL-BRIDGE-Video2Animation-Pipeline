"""
run.py -- the whole pipeline, or any single stage.

    python run.py                          # all 4 stages, in order
    python run.py --stage download         # 1. PSL videos   -> output/videos/
    python run.py --stage animate          # 2. Animics .glb -> output/animations/
    python run.py --stage retarget         # 3. onto your character (Blender)
    python run.py --stage merge            # 4. one <character>_animations.glb
    python run.py --stage retarget --category verbs   # stage 3 for one folder

Every stage is resume-safe: work that already exists is skipped, so after a
stop or crash just run the same command again.

Edit config.py to choose categories, trim, character and bone settings.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline"))

import config  # noqa: E402
from common import category_slug, videos_dir_for, animations_dir_for  # noqa: E402

STAGES = ["download", "animate", "retarget", "merge"]


def stage_download():
    import stage1_download
    print("\n########## STAGE 1: DOWNLOAD PSL VIDEOS ##########")
    stage1_download.download_all(config.CATEGORIES)
    return True


def stage_animate():
    import stage2_animate
    print("\n########## STAGE 2: CONVERT TO ANIMATIONS (Animics) ##########")
    stage2_animate.animate_all(config.CATEGORIES)
    return True


def stage_retarget(category=None):
    import stage3_retarget
    print("\n########## STAGE 3: RETARGET ONTO YOUR CHARACTER (Blender) ##########")
    return stage3_retarget.retarget_all(only=category)


def stage_merge():
    import stage4_merge
    print("\n########## STAGE 4: MERGE INTO ONE FILE ##########")
    stage4_merge.merge_all()
    return True


def main():
    parser = argparse.ArgumentParser(description="PSL video -> character animation pipeline")
    parser.add_argument("--stage", choices=STAGES,
                        help="run only this stage (default: all stages in order)")
    parser.add_argument("--category",
                        help="retarget stage only: limit to this one folder in output/animations/")
    args = parser.parse_args()

    if args.stage in (None, "download", "animate"):
        if not config.CATEGORIES:
            print("config.CATEGORIES is empty - add at least one category URL in config.py")
            return 1
        print("Categories in this run:")
        for url, words in config.CATEGORIES.items():
            what = "whole category" if words is None else f"{len(words)} word(s)"
            print(f"  - {category_slug(url)}  ({what})")
        print(f"  videos     -> {os.path.dirname(videos_dir_for('x'))}")
        print(f"  animations -> {os.path.dirname(animations_dir_for('x'))}")

    steps = {
        "download": stage_download,
        "animate": stage_animate,
        "retarget": lambda: stage_retarget(args.category),
        "merge": stage_merge,
    }
    for name in ([args.stage] if args.stage else STAGES):
        if not steps[name]():
            print(f"\nStopped: the {name} stage did not finish. Run it again to resume.")
            return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
