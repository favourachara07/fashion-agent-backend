import os
import glob
from app.core.database import SessionLocal
from app.models.wardrobe import WardrobeItem

def clean():
    db = SessionLocal()
    items = db.query(WardrobeItem).all()
    
    seen_bases = set()
    seeded_ids = {"garment3.jpg", "garment 2.jpg", "black_trousers.jpg"}
    
    for item in items:
        # Determine the base name (e.g., ignore the uuid prefix if present)
        # uuid is 32 chars + '_'
        base_name = item.item_id
        if len(base_name) > 33 and base_name[32] == '_':
            base_name = base_name[33:]
            
        # If we already have this base name, or it's a duplicate of a seeded item
        if base_name in seen_bases or base_name in seeded_ids:
            db.delete(item)
            file_path = os.path.join("uploaded_wardrobe", item.item_id)
            if os.path.exists(file_path):
                os.remove(file_path)
            print(f"Removed duplicate DB item and file: {item.item_id}")
        else:
            seen_bases.add(base_name)
    
    db.commit()
    db.close()
    
    # Clean avatar files
    avatars = glob.glob("uploaded_wardrobe/avatar_*.jpg")
    for f in avatars:
        os.remove(f)
    print(f"Removed {len(avatars)} temporary avatar images.")
    
    # Clean output files
    outputs = glob.glob("output/*.png")
    for f in outputs:
        os.remove(f)
    print(f"Removed {len(outputs)} old VTON outputs.")
    
    # Move unused raw images from root to a folder
    os.makedirs("test_images", exist_ok=True)
    root_jpgs = glob.glob("*.jpg")
    for f in root_jpgs:
        # Keep favour-2026.jpg and garment3.jpg in root for the test script
        if f not in ["favour-2026.jpg", "garment3.jpg"]:
            os.rename(f, os.path.join("test_images", f))
            print(f"Moved {f} to test_images/")
            
    print("Cleanup complete!")

if __name__ == "__main__":
    clean()
