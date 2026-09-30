"""
Full Pipeline Test for Fashion Agent Backend
=============================================
Tests the complete 3-phase workflow:
  Phase 1: Upload garment → Kaggle Qwen2-VL digitizes → SQLite stores
  Phase 2: Generate 7-day plan → LangGraph pauses before VTON
  Phase 3: Approve plan → VTON rendering on Kaggle GPU

Prerequisites:
  1. FastAPI server running: python -m uvicorn app.main:app --port 8000
  2. Kaggle notebook running with ngrok tunnel
  3. KAGGLE_GPU_URL set in .env to the active ngrok URL
"""

import requests
import json
import os
import sys
import time

LOCAL_API_URL = "http://127.0.0.1:8000"

# Test images — these should exist in the project root
AVATAR_IMAGE_PATH = "favour-2026.jpg"
NEW_GARMENT_PATH = "garment3.jpg"

TOKEN = None

def get_token():
    """Authenticate with the server and retrieve a JWT."""
    print("=== AUTHENTICATING ===\n")
    data = {"username": "testuser", "password": "password123"}
    try:
        resp = requests.post(f"{LOCAL_API_URL}/auth/token", data=data, timeout=5)
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            print("[+] Successfully authenticated as 'testuser'.")
            return token
        else:
            print(f"[-] Authentication failed: {resp.text}")
            return None
    except Exception as e:
        print(f"[-] Auth error: {e}")
        return None


def check_prerequisites():
    """Verify the server is running and test images exist."""
    print("=== CHECKING PREREQUISITES ===\n")
    
    if not os.path.exists(AVATAR_IMAGE_PATH):
        print(f"[-] Local avatar image not found: {AVATAR_IMAGE_PATH}")
        print("    [*] Will rely on backend default_avatar.jpg fallback.")
    else:
        print(f"[+] Avatar: {AVATAR_IMAGE_PATH}")
    print(f"[+] Garment: {NEW_GARMENT_PATH}")
    
    try:
        resp = requests.get(f"{LOCAL_API_URL}/", timeout=5)
        health = resp.json()
        print(f"[+] Server: {health['status']}")
        print(f"[+] Kaggle GPU URL: {health.get('kaggle_gpu_url', 'NOT SET')}")
        return True
    except requests.exceptions.ConnectionError:
        print("[-] Cannot connect to FastAPI server. Is it running?")
        print("    Run: python -m uvicorn app.main:app --port 8000")
        return False


def test_phase_0_wardrobe():
    """Phase 0: Check existing wardrobe contents."""
    print("\n=== PHASE 0: CHECKING WARDROBE ===\n")
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    resp = requests.get(f"{LOCAL_API_URL}/wardrobe", headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        print(f"[+] Wardrobe contains {data['count']} items:")
        for item in data["items"]:
            print(f"    - {item['item_id']}: {item['color']} {item['category']} ({item['style']})")
        return data
    else:
        print(f"[-] Failed: {resp.status_code} - {resp.text}")
        return None


def test_phase_1_ingest(garment_path: str):
    """Phase 1: Upload a garment to the digital closet via Kaggle Qwen2-VL."""
    print("\n=== PHASE 1: WARDROBE INGESTION ===\n")
    print(f"[*] Uploading '{garment_path}' → Kaggle Qwen2-VL → SQLite...")
    
    with open(garment_path, "rb") as garment_file:
        files = {"garment_image": (os.path.basename(garment_path), garment_file, "image/jpeg")}
        headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
        try:
            resp = requests.post(f"{LOCAL_API_URL}/add-wardrobe-item", files=files, headers=headers, timeout=120)
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"[+] Success! Item added: {data['item_id']}")
                print(f"[+] AI Metadata: {json.dumps(data['extracted_data'], indent=2)}")
                return data
            else:
                print(f"[-] Failed ({resp.status_code}): {resp.text}")
                return None
        except requests.exceptions.Timeout:
            print("[-] Timeout — Kaggle GPU might need more time.")
            return None


def test_phase_2_plan():
    """Phase 2: Generate a 7-day outfit plan (graph pauses before VTON)."""
    print("\n=== PHASE 2: 7-DAY PLAN GENERATION ===\n")
    
    schedule = (
        "Monday: Office work, Tuesday: Gym then dinner, Wednesday: Casual meeting, "
        "Thursday: WFH, Friday: Friday night party, Saturday: Weekend brunch, Sunday: Rest"
    )
    print(f"[*] Schedule: {schedule[:80]}...")
    
    data = {"user_schedule": schedule}
    files = None
    
    if os.path.exists(AVATAR_IMAGE_PATH):
        avatar_file = open(AVATAR_IMAGE_PATH, "rb")
        files = {"user_avatar": (os.path.basename(AVATAR_IMAGE_PATH), avatar_file, "image/jpeg")}
        
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
        resp = requests.post(f"{LOCAL_API_URL}/generate-plan", files=files, data=data, headers=headers, timeout=120)
            
        if resp.status_code == 200:
            result = resp.json()
            thread_id = result["thread_id"]
            plan = result.get("weekly_plan", {})
            
            print(f"[+] Status: {result['status']}")
            print(f"[+] Thread ID: {thread_id}")
            print(f"[+] Weekly Plan:")
            for day in plan.get("plan", []):
                print(f"    {day['day']}: top={day['top_id']}, bottom={day['bottom_id']}")
                print(f"      Reason: {day['reasoning'][:80]}...")
            
            return thread_id
        else:
            print(f"[-] Failed ({resp.status_code}): {resp.text}")
            return None
    except requests.exceptions.Timeout:
        print("[-] Timeout generating plan.")
        return None
    finally:
        if 'avatar_file' in locals() and not avatar_file.closed:
            avatar_file.close()

def test_phase_3_approve(thread_id: str):
    """Phase 3: Approve the plan and trigger VTON rendering."""
    print("\n=== PHASE 3: APPROVE & RENDER VTON ===\n")
    
    user_input = input("[?] Approve this plan? (y/n): ").strip().lower()
    approved = user_input in ("y", "yes", "")
    
    payload = {"thread_id": thread_id, "approved": approved}
    
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
        resp = requests.post(
            f"{LOCAL_API_URL}/resume-plan",
            json=payload,
            headers=headers,
            timeout=10 
        )
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"[+] Status: {result['status']}")
            
            if result["status"] == "processing":
                print("[*] Polling for background job completion...")
                while True:
                    time.sleep(10)
                    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
                    status_resp = requests.get(f"{LOCAL_API_URL}/vton-status/{thread_id}", headers=headers, timeout=10)
                    if status_resp.status_code == 200:
                        progress = status_resp.json()
                        state = progress.get("status")
                        
                        if state == "processing":
                            print(f"    [~] Generating... {progress.get('progress')}/{progress.get('total')} complete.")
                        elif state == "completed":
                            print(f"\n[+] Job Finished!")
                            vton_paths = progress.get("images", [])
                            print(f"[+] Generated {len(vton_paths)} VTON images:")
                            for path in vton_paths:
                                print(f"    - {LOCAL_API_URL}/vton/{path}")
                            break
                        elif state == "error":
                            print(f"\n[-] Background job failed: {progress.get('error')}")
                            break
                        else:
                            print(f"\n[-] Unknown state: {state}")
                            break
                    else:
                        print(f"[-] Status endpoint error: {status_resp.status_code}")
                        break
                return result
            else:
                print(f"[+] {result.get('message', '')}")
                return result
        else:
            print(f"[-] Failed ({resp.status_code}): {resp.text}")
            return None
    except Exception as e:
        print(f"[-] Error during VTON execution: {e}")
        return None


def main():
    if not check_prerequisites():
        sys.exit(1)
        
    global TOKEN
    TOKEN = get_token()
    if not TOKEN:
        sys.exit(1)
    
    test_phase_0_wardrobe()
    
    # Phase 1: Ingest (requires Kaggle)
    ingest_input = input("\n[?] Run Phase 1 (Wardrobe Ingestion via Kaggle)? (y/n): ").strip().lower()
    if ingest_input in ("y", "yes"):
        new_clothes_dir = "new_clothes"
        os.makedirs(new_clothes_dir, exist_ok=True)
        images = [f for f in os.listdir(new_clothes_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        if not images:
            print(f"    [-] No images found in '{new_clothes_dir}/' directory. Please add some and try again.")
        else:
            print(f"    [*] Found {len(images)} images in '{new_clothes_dir}/'. Processing...")
            import shutil
            os.makedirs("test_images", exist_ok=True)
            for img in images:
                img_path = os.path.join(new_clothes_dir, img)
                success = test_phase_1_ingest(img_path)
                if success:
                    # Move to test_images after successful ingestion so it isn't processed again
                    shutil.move(img_path, os.path.join("test_images", img))
                    print(f"    [+] Moved {img} to test_images/")
            test_phase_0_wardrobe()  # Show updated wardrobe
    
    # Phase 2: Plan generation (requires Gemini API)
    plan_input = input("\n[?] Run Phase 2 (7-Day Plan Generation)? (y/n): ").strip().lower()
    if plan_input in ("y", "yes"):
        thread_id = test_phase_2_plan()
        
        if thread_id:
            # Phase 3: Approve and render (requires Kaggle)
            test_phase_3_approve(thread_id)
    
    print("\n=== TEST COMPLETE ===")


if __name__ == "__main__":
    main()