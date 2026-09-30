import requests

# 1. Configuration
# We are hitting the Kaggle Ngrok URL directly for this test to isolate the ML pipeline
KAGGLE_NGROK_URL = "https://unmatured-postdiphtheritic-larisa.ngrok-free.dev" # REPLACE THIS with your active Kaggle URL
ENDPOINT = f"{KAGGLE_NGROK_URL}/try-on"

# Paths to the two images on your PC
AVATAR_IMAGE_PATH = "favour-2026.jpg"
GARMENT_IMAGE_PATH = "garment3.jpg"

def test_image_conditioned_pipeline():
    print(f"[*] Sending Avatar and Garment to Kaggle GPU...")
    print(f"[*] Endpoint: {ENDPOINT}")
    
    try:
        # 2. Open both images in binary read mode
        with open(AVATAR_IMAGE_PATH, "rb") as avatar_file, \
             open(GARMENT_IMAGE_PATH, "rb") as garment_file:
            
            # 3. Package them into a multipart form data payload
            # The keys ('user_avatar', 'garment_image') MUST match your FastAPI parameters
            files = {
                "user_avatar": (AVATAR_IMAGE_PATH, avatar_file, "image/jpeg"),
                "garment_image": (GARMENT_IMAGE_PATH, garment_file, "image/jpeg")
            }
            
            # 4. Fire the request
            # High timeout because SDXL with IP-Adapter is heavy
            response = requests.post(ENDPOINT, files=files, timeout=240)
            
            if response.status_code == 200:
                output_filename = "image_conditioned_output.png"
                with open(output_filename, "wb") as out_file:
                    out_file.write(response.content)
                print(f"[+] Success! New fit saved as '{output_filename}'")
            else:
                print(f"[-] Server Error ({response.status_code}): {response.text}")
                
    except requests.exceptions.Timeout:
        print("[-] Error: The request timed out. SDXL might need more time on the T4 GPU.")
    except Exception as e:
        print(f"[-] Connection Error: {e}")

if __name__ == "__main__":
    test_image_conditioned_pipeline()