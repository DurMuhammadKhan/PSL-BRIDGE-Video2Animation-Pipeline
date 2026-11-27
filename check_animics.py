"""
check_animics.py -- quick "is Animics healthy right now?" probe.

animics.gti.upf.edu is a shared research server. When it is overloaded it still
serves its HTML, but the in-browser editor + default character never finish
initializing, so every animate session times out. Run this BEFORE a big batch:

    python check_animics.py

  HEALTHY   -> go ahead and run `python run.py`
  DEGRADED  -> the server is too slow right now; try again later (off-peak)

Exit code is 0 when healthy, 1 when degraded, so you can also gate a run:
    python check_animics.py && python run.py
"""
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

ANIMICS_URL = "https://animics.gti.upf.edu/"

# How long to give the server to bring up the editor AND load the default
# character. On a healthy day this happens in well under a minute.
READY_TIMEOUT_SEC = 120

READY_JS = (
    "var a=window.global&&window.global.app;"
    "return !!(a&&a.editor&&a.videoProcessor&&a.editor.currentCharacter);"
)


def main():
    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument("--window-size=700,500")

    driver = webdriver.Chrome(options=options)
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            driver.command_executor.set_timeout(READY_TIMEOUT_SEC + 60)
    except Exception:
        pass
    driver.set_page_load_timeout(READY_TIMEOUT_SEC + 60)

    t0 = time.time()
    try:
        driver.get(ANIMICS_URL)
        print(f"page responded in {time.time() - t0:.0f}s", flush=True)

        # Click "Keyframe" to start a project (the editor only initializes then).
        try:
            driver.execute_script("document.getElementById('keyframe-project').click();")
        except Exception:
            print("DEGRADED - could not even reach the 'Keyframe' button in time.")
            return 1

        end = time.time() + READY_TIMEOUT_SEC
        while time.time() < end:
            try:
                if driver.execute_script(READY_JS):
                    print(f"HEALTHY - editor + character ready in {time.time() - t0:.0f}s. "
                          f"Safe to run: python run.py")
                    return 0
            except Exception:
                pass
            time.sleep(3)

        print(f"DEGRADED - editor/character did not initialize within "
              f"{READY_TIMEOUT_SEC}s. The server is overloaded; try again later.")
        return 1
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
