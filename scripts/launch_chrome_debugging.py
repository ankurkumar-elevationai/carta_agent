import subprocess
import os
import sys
import time
import urllib.request

def launch_chrome():
    print("=== Launching Chrome with Remote Debugging ===")
    
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
        print("❌ Error: Could not find Google Chrome installation path.")
        return False
        
    print(f"Found Chrome: {chrome_exe}")
    
    # 2. Resolve User Profile Path
    user_data_dir = os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data")
    print(f"Using Default Chrome Profile: {user_data_dir}")
    
    # 3. Kill existing Chrome processes (so Chrome starts fresh and binds to port 9222)
    print("Closing all existing Chrome processes to enable remote debugging...")
    if sys.platform == "win32":
        subprocess.run("taskkill /f /im chrome.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        
    # 4. Launch Chrome with port 9222 and user profile
    cmd = [
        chrome_exe,
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Chrome launched successfully.")
    
    # 5. Wait for port 9222 to become active
    print("Waiting for port 9222 to become active...")
    for i in range(15):
        try:
            urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1)
            print("[OK] Chrome is now active and listening on port 9222!")
            return True
        except Exception:
            time.sleep(1)
            
    print("❌ Warning: Port 9222 did not respond. Try running Chrome as Administrator or relaunch manually.")
    return False

if __name__ == "__main__":
    launch_chrome()
