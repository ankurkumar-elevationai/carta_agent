import subprocess
import os
import sys
import time
import urllib.request

def relaunch_user_chrome():
    print("=== Relaunching your normal Chrome with debugging enabled ===")
    
    # 1. Resolve Chrome Path
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    
    chrome_exe = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome_exe = p
            break
            
    if not chrome_exe:
        print("[ERROR] Could not find Google Chrome installation path.")
        return False
        
    # 2. Terminate all Chrome instances and wait for locks to release
    print("Force closing Chrome to release profile locks...")
    user_data = os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data")
    lock_file = os.path.join(user_data, "lockfile")
    
    if sys.platform == "win32":
        subprocess.run("taskkill /f /im chrome.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Wait up to 10 seconds for the OS to release file locks
        lock_released = False
        for i in range(10):
            if not os.path.exists(lock_file):
                lock_released = True
                break
            try:
                # Attempt to delete the lock file to verify it is unlocked
                os.remove(lock_file)
                print("[OK] Lockfile released and removed.")
                lock_released = True
                break
            except OSError:
                print(f"Waiting for Chrome process locks to release... ({i+1}/10)")
                time.sleep(1)
                
        if not lock_released:
            print("[WARN] Chrome lockfile is still held by a process. Proceeding anyway...")
        else:
            time.sleep(1.5)  # Give extra breathing room for socket cleanup
        
    # 3. Launch Chrome using your default profile with debugging enabled
    # We do NOT pass a custom user-data-dir so it loads your exact normal Chrome profile
    cmd = [
        chrome_exe,
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        r"--user-data-dir=C:\Users\iaman\AppData\Local\Google\Chrome\User Data",
        "--restore-last-session",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-software-rasterizer"
    ]
    
    print(f"Launching Chrome: {' '.join(cmd)}")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 4. Wait for port 9222
    print("Waiting for port 9222 to respond...")
    for i in range(10):
        try:
            urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1)
            print("[OK] Chrome is ready on port 9222 with your normal logged-in session!")
            return True
        except Exception:
            time.sleep(1)
            
    print("[ERROR] Port 9222 did not open. Please manually close Chrome and run this command in cmd:")
    print(f'"{chrome_exe}" --remote-debugging-port=9222')
    return False

if __name__ == "__main__":
    relaunch_user_chrome()
