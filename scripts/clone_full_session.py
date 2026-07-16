import os
import shutil
import subprocess
import sys
import time

def clean_dir(path):
    if os.path.exists(path):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception as e:
            print(f"Warning: could not clean {path}: {e}")

def clone_full_session():
    print("=== Cloning Chrome Session and Storage to Debug Profile ===")
    
    src_user_data = os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data")
    dest_user_data = os.path.join(os.getcwd(), "chrome_profile")
    
    # 1. Kill Chrome processes to release database and storage locks
    print("Closing Google Chrome to release all file locks...")
    if sys.platform == "win32":
        subprocess.run("taskkill /f /im chrome.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        
    # Paths to copy
    # Local State
    src_local_state = os.path.join(src_user_data, "Local State")
    dest_local_state = os.path.join(dest_user_data, "Local State")
    
    # Default directories and files
    targets = [
        ("Network/Cookies", "Default/Network/Cookies", False),
        ("Local Storage", "Default/Local Storage", True),
        ("IndexedDB", "Default/IndexedDB", True),
        ("Session Storage", "Default/Session Storage", True)
    ]
    
    try:
        # Copy Local State
        if os.path.exists(src_local_state):
            clean_dir(dest_local_state)
            shutil.copy2(src_local_state, dest_local_state)
            print("[OK] Local State copied.")
        else:
            print("[ERROR] Local State not found.")
            return False
            
        # Copy each target
        for name, rel_path, is_dir in targets:
            src = os.path.join(src_user_data, "Default", name) if not name.startswith("Default") else os.path.join(src_user_data, rel_path)
            dest = os.path.join(dest_user_data, rel_path)
            
            # Check old cookies path fallback
            if name == "Network/Cookies" and not os.path.exists(src):
                src = os.path.join(src_user_data, "Default", "Cookies")
                
            if os.path.exists(src):
                clean_dir(dest)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                
                if is_dir:
                    shutil.copytree(src, dest)
                    print(f"[OK] Directory {name} copied.")
                else:
                    shutil.copy2(src, dest)
                    print(f"[OK] File {name} copied.")
            else:
                print(f"[INFO] {name} not found at {src}, skipping.")
                
        print("[OK] Session and Storage cloned successfully!")
        return True
    except Exception as e:
        print(f"[ERROR] Error copying session files: {e}")
        return False

if __name__ == "__main__":
    clone_full_session()
