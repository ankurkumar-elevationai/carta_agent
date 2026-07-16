import subprocess
import time
import os
import urllib.request
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.providers.carta.utils.settings import settings



def start_persistent_browser():
    """
    Launch Chrome with a persistent user profile and remote debugging
    enabled on port 9222. The browser stays open while this script runs.

    After launch, log in to Carta manually in the opened browser window.
    The CartaProvider will reuse the authenticated session automatically.
    """
    if sys.platform == "win32":
        chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(chrome_exe):
            chrome_exe = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    elif sys.platform == "darwin":
        chrome_exe = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    else:
        chrome_exe = "google-chrome"

    user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
    os.makedirs(user_data_dir, exist_ok=True)

    print(f"Using profile: {user_data_dir}")
    print("Launching Chrome on port 9222 -> playground.carta.team ...")

    proc = subprocess.Popen(
        [
            chrome_exe,
            "--remote-debugging-port=9222",
            "--remote-allow-origins=*",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--mute-audio",
            "--disable-background-networking",
            "--disable-sync",
            "--metrics-recording-only",
            f"{settings.login_base_url}/credentials/login/",  # Start on Carta login page
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(3)

    for i in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2)
            print("[OK] Chrome ready with CDP on port 9222")
            break
        except Exception:
            time.sleep(1)
    else:
        print("[ERR] CDP not available after 30s")
        proc.terminate()
        return

    print()
    print("Log in to Carta manually in the opened browser window.")
    print("   Once authenticated, keep this window open.")
    print("   The CartaProvider will reuse the session automatically.")
    print()
    print("Press Ctrl+C to stop the browser.")

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("Stopping browser...")
        proc.terminate()


if __name__ == "__main__":
    start_persistent_browser()
