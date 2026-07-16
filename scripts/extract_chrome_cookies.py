import os
import json
import sqlite3
import shutil
import base64
import ctypes
from ctypes import wintypes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Windows DPAPI structures
class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ('cbData', wintypes.DWORD),
        ('pbData', ctypes.POINTER(ctypes.c_char))
    ]

def decrypt_key_with_dpapi(encrypted_key):
    # The key starts with b'DPAPI' prefix (5 bytes)
    encrypted_key = encrypted_key[5:]
    
    in_blob = DATA_BLOB(len(encrypted_key), ctypes.create_string_buffer(encrypted_key))
    out_blob = DATA_BLOB()
    
    # CRYPTPROTECT_UI_FORBIDDEN = 1
    success = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        1,
        ctypes.byref(out_blob)
    )
    if not success:
        raise Exception("DPAPI decryption failed")
        
    decrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return decrypted

def get_encryption_key():
    local_state_path = os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data\Local State")
    if not os.path.exists(local_state_path):
        raise FileNotFoundError(f"Local State file not found at: {local_state_path}")
        
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.loads(f.read())
        
    encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    return decrypt_key_with_dpapi(encrypted_key)

def decrypt_cookie_value(encrypted_value, key):
    try:
        # Check prefix 'v10' or 'v11'
        prefix = encrypted_value[:3]
        if prefix in (b'v10', b'v11'):
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:]
            aesgcm = AESGCM(key)
            decrypted = aesgcm.decrypt(nonce, ciphertext, None)
            return decrypted.decode('utf-8')
    except Exception as e:
        return f"[Decryption Error: {e}]"
    return ""

def extract_cookies():
    print("=== Extracting Carta Session Cookies from Chrome Profile ===")
    
    user_data_dir = os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data")
    if not os.path.exists(user_data_dir):
        print(f"[ERROR] Chrome User Data directory not found: {user_data_dir}")
        return False
        
    # Scan for potential profiles
    profiles = [d for d in os.listdir(user_data_dir) 
                if os.path.isdir(os.path.join(user_data_dir, d)) and (d == "Default" or d.startswith("Profile "))]
                
    best_profile = None
    best_score = -1
    cookies_db_path = None
    
    for profile in profiles:
        db_paths = [
            os.path.join(user_data_dir, profile, "Network", "Cookies"),
            os.path.join(user_data_dir, profile, "Cookies")
        ]
        
        profile_db = None
        for p in db_paths:
            if os.path.exists(p):
                profile_db = p
                break
                
        if not profile_db:
            continue
            
        # Copy to temp to check
        temp_db_path = os.path.join(os.getcwd(), f"temp_check_{profile}.sqlite")
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except Exception:
                pass
                
        try:
            shutil.copy2(profile_db, temp_db_path)
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            
            # Check for eshares-sessionid-2
            cursor.execute("SELECT COUNT(*) FROM cookies WHERE (host_key LIKE '%carta.com' OR host_key LIKE '%carta.team') AND name = 'eshares-sessionid-2'")
            has_session = cursor.fetchone()[0] > 0
            
            # Count total carta cookies
            cursor.execute("SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%carta.com' OR host_key LIKE '%carta.team'")
            total_carta = cursor.fetchone()[0]
            
            conn.close()
            
            # Score: session cookie is highly preferred
            score = (1000 if has_session else 0) + total_carta
            if score > best_score and total_carta > 0:
                best_score = score
                best_profile = profile
                cookies_db_path = profile_db
                
        except Exception as e:
            print(f"[WARN] Error scanning profile {profile}: {e}")
        finally:
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass
                    
    if not best_profile:
        print("[ERROR] No profiles with carta.com or carta.team cookies found.")
        return False
        
    print(f"[INFO] Selected Chrome Profile: '{best_profile}' (score: {best_score})")
    
    # Copy selected profile database to temp path
    temp_db_path = os.path.join(os.getcwd(), "temp_cookies_db.sqlite")
    if os.path.exists(temp_db_path):
        try:
            os.remove(temp_db_path)
        except Exception:
            pass
            
    try:
        shutil.copy2(cookies_db_path, temp_db_path)
        key = get_encryption_key()
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        # Query for all cookies related to carta.com or carta.team
        cursor.execute("""
            SELECT host_key, name, path, encrypted_value, expires_utc, is_secure, is_httponly, samesite 
            FROM cookies 
            WHERE host_key LIKE '%carta.com' OR host_key LIKE '%carta.team'
        """)
        
        playwright_cookies = []
        for row in cursor.fetchall():
            host_key, name, path, encrypted_val, expires_utc, is_secure, is_httponly, samesite_val = row
            
            decrypted_val = decrypt_cookie_value(encrypted_val, key)
            if not decrypted_val:
                continue
            if decrypted_val.startswith("[Decryption Error"):
                print(f"[WARN] Decryption error for cookie '{name}': {decrypted_val}")
                continue
                
            # Convert expires_utc (webkit epoch) to unix epoch
            # Webkit epoch starts Jan 1, 1601. Unix starts Jan 1, 1700 / 1970.
            # expires_utc is in microseconds.
            expires_seconds = -1
            if expires_utc > 0:
                expires_seconds = int((expires_utc / 1000000) - 11644473600)
                
            # Convert samesite integer to string: -1: "None", 0: "Neutral", 1: "Strict", 2: "Lax"
            samesite_str = "Lax"
            if samesite_val == -1:
                samesite_str = "None"
            elif samesite_val == 1:
                samesite_str = "Strict"
                
            cookie_dict = {
                "name": name,
                "value": decrypted_val,
                "domain": host_key,
                "path": path,
                "secure": bool(is_secure),
                "httpOnly": bool(is_httponly),
                "sameSite": samesite_str
            }
            if expires_seconds > 0:
                cookie_dict["expires"] = expires_seconds
                
            playwright_cookies.append(cookie_dict)
            
        conn.close()
        
        # Write to session_cookies.json
        output_path = os.path.join(os.getcwd(), "config", "session_cookies.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(playwright_cookies, f, indent=2)
            
        print(f"[OK] Extracted {len(playwright_cookies)} cookies for 'carta.com'")
        print(f"[OK] Session cookies written to: {output_path}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Cookie extraction failed: {e}")
        return False
        
    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

if __name__ == "__main__":
    extract_cookies()
