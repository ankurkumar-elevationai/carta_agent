import os
import shutil
import subprocess
import sys
import time

def clone_session():
    print("=== Cloning Chrome Session to Debug Profile ===")
    
    src_user_data = os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data")
    dest_user_data = os.path.join(os.getcwd(), "chrome_profile")
    
    # Files to copy
    # 1. Local State (contains the DPAPI encrypted key)
    src_local_state = os.path.join(src_user_data, "Local State")
    dest_local_state = os.path.join(dest_user_data, "Local State")
    
    # 2. Cookies database
    src_cookies = os.path.join(src_user_data, "Default", "Network", "Cookies")
    dest_cookies = os.path.join(dest_user_data, "Default", "Network", "Cookies")
    
    # Create destination directories
    os.makedirs(os.path.dirname(dest_local_state), exist_ok=True)
    os.makedirs(os.path.dirname(dest_cookies), exist_ok=True)
    
    # Kill Chrome processes to release file locks on databases
    print("Closing Google Chrome to release database locks...")
    if sys.platform == "win32":
        subprocess.run("taskkill /f /im chrome.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        
    # Copy files
    try:
        if os.path.exists(src_local_state):
            shutil.copy2(src_local_state, dest_local_state)
            print("[OK] Local State copied.")
        else:
            print("[ERROR] Local State not found.")
            return False
            
        if os.path.exists(src_cookies):
            shutil.copy2(src_cookies, dest_cookies)
            print("[OK] Cookies database copied.")
        else:
            # Check fallback path (older chrome versions had cookies directly in Default folder)
            src_cookies_old = os.path.join(src_user_data, "Default", "Cookies")
            if os.path.exists(src_cookies_old):
                shutil.copy2(src_cookies_old, dest_cookies)
                print("[OK] Cookies database copied (from fallback path).")
            else:
                print("[ERROR] Cookies database not found.")
                return False
                
        print("[OK] Session cloned successfully!")
        return True
    except Exception as e:
        print(f"[ERROR] Error copying session files: {e}")
        return False

if __name__ == "__main__":
    clone_session()
