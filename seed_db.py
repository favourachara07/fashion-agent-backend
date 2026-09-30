# seed_db.py
from app.core.database import SessionLocal
from app.models.wardrobe import WardrobeItem

import shutil
import os

def seed_database():
    db = SessionLocal()
    
    # The garments you just tested in Kaggle
    test_items = [
        WardrobeItem(item_id="garment3.jpg", category="top", style="casual plaid", color="yellow and blue", description="A long-sleeve yellow and dark blue plaid button-up shirt"),
        WardrobeItem(item_id="garment 2.jpg", category="top", style="smart casual button-up", color="dark grey", description="A dark grey short-sleeve button-up shirt with a grandad collar"),
        WardrobeItem(item_id="black_trousers.jpg", category="bottom", style="formal tailored", color="black", description="Sharp tailored black dress trousers")
    ]
    
    # Check if data already exists to prevent duplicates
    existing_items = db.query(WardrobeItem).count()
    if existing_items == 0:
        db.add_all(test_items)
        db.commit()
        
        # Ensure the physical files exist in uploaded_wardrobe/
        os.makedirs("uploaded_wardrobe", exist_ok=True)
        for item in test_items:
            src = item.item_id
            dst = os.path.join("uploaded_wardrobe", item.item_id)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"[+] Copied {src} to uploaded_wardrobe/")
        
        print("[+] Successfully seeded SQLite database with test garments.")
    else:
        print("[!] Database already contains items. Skipping seed.")
        
    db.close()

if __name__ == "__main__":
    seed_database()