"""
config.py -- The ONLY file you normally need to edit.

Add one or more PSL dictionary category URLs below. For each category you can
either download the WHOLE category, or just a few specific words.

For every category the pipeline creates two folders NEXT TO these scripts:
    <category>_videos/       <- PSL .mp4 clips are downloaded here
    <category>_animations/   <- Animics .glb animations are exported here

e.g. for "https://psl.org.pk/dictionary/10-around-the-house" you get
    around-the-house_videos/  and  around-the-house_animations/
"""

# ---------------------------------------------------------------------------
# CATEGORIES: {category_url: words}
#   words = None          -> download the WHOLE category
#   words = ["a", "b"]    -> download only those specific words (case-insensitive)
#
# You can list as many categories as you want.
# ---------------------------------------------------------------------------
CATEGORIES = {
    "https://psl.org.pk/dictionary/11-arts": None,
    "https://psl.org.pk/dictionary/76-automobile":None,
    "https://psl.org.pk/dictionary/12-banking":None,
    "https://psl.org.pk/dictionary/13-bathroom":None,
    "https://psl.org.pk/dictionary/14-beach":None,
    "https://psl.org.pk/dictionary/15-beauty":None,
    "https://psl.org.pk/dictionary/16-bedroom":None,
    "https://psl.org.pk/dictionary/17-birds":None,
    "https://psl.org.pk/dictionary/32-family-marriage":None,
    "https://psl.org.pk/dictionary/33-famous-people":None,
    "https://psl.org.pk/dictionary/34-farming-agriculture":None,
    "https://psl.org.pk/dictionary/35-flowers-plants-trees":None,
    "https://psl.org.pk/dictionary/36-food-general":None,
    "https://psl.org.pk/dictionary/37-food-dishes":None,
    "https://psl.org.pk/dictionary/38-fruits":None,
    "https://psl.org.pk/dictionary/39-geography":None,
    "https://psl.org.pk/dictionary/40-government":None,
    "https://psl.org.pk/dictionary/41-grammar":None,
    "https://psl.org.pk/dictionary/42-health-medical-care":None,
    "https://psl.org.pk/dictionary/43-holidays-celebrations":None,
    "https://psl.org.pk/dictionary/78-hospitality":None,
    "https://psl.org.pk/dictionary/44-hygiene":None,
    "https://psl.org.pk/dictionary/45-insects-spiders-reptiles":None,
    "https://psl.org.pk/dictionary/83-islamic-signs":None,
    "https://psl.org.pk/dictionary/46-jewelry":None,
    "https://psl.org.pk/dictionary/47-kitchen":None,
    "https://psl.org.pk/dictionary/48-law-order":None,
    "https://psl.org.pk/dictionary/49-life-skills-training":None,
    "https://psl.org.pk/dictionary/50-living-room":None,
    "https://psl.org.pk/dictionary/51-mammals":None,
    "https://psl.org.pk/dictionary/52-marine-life":None,
    "https://psl.org.pk/dictionary/53-mathematics":None,
    "https://psl.org.pk/dictionary/54-media":None,
    "https://psl.org.pk/dictionary/55-military":None,
    "https://psl.org.pk/dictionary/56-music-dance":None,
    "https://psl.org.pk/dictionary/57-nouns-general":None,
    "https://psl.org.pk/dictionary/58-numbers":None,
    "https://psl.org.pk/dictionary/59-office":None,
    "https://psl.org.pk/dictionary/60-pakistan-places":None,
    "https://psl.org.pk/dictionary/61-prepositions":None,
    "https://psl.org.pk/dictionary/61-prepositions":None,
    "https://psl.org.pk/dictionary/63-pronouns":None,
    "http://psl.org.pk/dictionary/64-science":None,
    "https://psl.org.pk/dictionary/71-vegetables": None,
    "https://psl.org.pk/dictionary/72-verbs": None,
    "https://psl.org.pk/dictionary/74-vocational": None,
    "https://psl.org.pk/dictionary/73-weather": None,
    "https://psl.org.pk/dictionary/21-burger-king": None,
    "https://psl.org.pk/dictionary/81-kfc": None,
}

# ---------------------------------------------------------------------------
# DOWNLOAD (PSL) settings
# ---------------------------------------------------------------------------
SHOW_BROWSER_DOWNLOAD = False   # True -> watch the download browser (debugging)

# ---------------------------------------------------------------------------
# ANIMATION (Animics) settings
# ---------------------------------------------------------------------------
# Each clip is trimmed to [START, END] of its duration before pose extraction.
#   first 50%  -> START=0.0, END=0.5   (default)
#   last  50%  -> START=0.5, END=1.0
#   middle 50% -> START=0.25, END=0.75
TRIM_START_RATIO = 0.0
TRIM_END_RATIO = 0.5

# Keep False on a machine with a real GPU (Animics uses WebGL + MediaPipe and
# is far more reliable with a visible browser). See README for EC2/headless.
HEADLESS_ANIMICS = False

# Restart Chrome every CHUNK_SIZE videos to bound WebGL/MediaPipe memory growth.
CHUNK_SIZE = 8

# How many Chrome instances to run at the SAME TIME per category (CPU/GPU heavy).
NUM_WORKERS = 1

# Chrome profile. Selenium reuses a PERSISTENT profile so the Animics character
# model + MediaPipe pose models stay cached on disk. A fresh profile every session
# re-downloads them cold every time, which stalls when animics.gti.upf.edu is slow.
# This is the #1 reason automation fails where your normal (already-cached) Chrome
# works fine.
#   None -> a dedicated persistent profile inside the project (.chrome-profile/).
#           The FIRST session warms it; after that, sessions start from cache.
#   path -> reuse your REAL Chrome profile's warm cache for instant loads. FULLY
#           QUIT Chrome first (Chrome won't share a profile with a running window).
#           Mac: "/Users/<you>/Library/Application Support/Google/Chrome"
CHROME_USER_DATA_DIR = None
CHROME_PROFILE_DIRECTORY = "Default"   # e.g. "Default" or "Profile 1"
