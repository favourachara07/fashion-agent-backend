import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from io import BytesIO
from app.services.orchestrator import fashion_agent, vton_job_progress
import httpx
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.wardrobe import WardrobeItem
from app.models.user import User
import uuid
from pydantic import BaseModel
from app.core.auth import get_current_user

router = APIRouter()

WARDROBE_DIR = "uploaded_wardrobe"
os.makedirs(WARDROBE_DIR, exist_ok=True)

KAGGLE_HEADERS = {"ngrok-skip-browser-warning": "true"}


def get_kaggle_url() -> str:
    """Get the Kaggle ngrok URL from environment, with validation."""
    url = os.getenv("KAGGLE_GPU_URL", "").rstrip("/")
    if not url or url == "https://your-ngrok-url.ngrok-free.dev":
        raise HTTPException(
            status_code=503,
            detail="KAGGLE_GPU_URL is not configured. Update your .env file with the active ngrok URL from your Kaggle notebook."
        )
    return url


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────
# WARDROBE MANAGEMENT
# ──────────────────────────────────────────────────────────────

@router.get("/wardrobe")
def list_wardrobe(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List all items in the user's digital closet."""
    items = db.query(WardrobeItem).filter(WardrobeItem.user_id == current_user.id).all()
    return {
        "count": len(items),
        "items": [
            {
                "item_id": item.item_id,
                "category": item.category,
                "style": item.style,
                "color": item.color,
                "description": item.description,
            }
            for item in items
        ],
    }


@router.get("/wardrobe/{item_id}/image")
def get_wardrobe_image(item_id: str, db: Session = Depends(get_db)):
    """Serve a garment image file from the uploaded_wardrobe directory."""
    # Verify the item exists in the database
    item = db.query(WardrobeItem).filter(WardrobeItem.item_id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found in database.")

    file_path = os.path.join(WARDROBE_DIR, item_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Image file for '{item_id}' not found on disk.")

    return FileResponse(file_path, media_type="image/jpeg")


@router.post("/add-wardrobe-item")
async def add_wardrobe_item(
    garment_image: UploadFile = File(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a garment image → Kaggle Qwen2-VL extracts metadata → saved to SQLite."""
    kaggle_url = get_kaggle_url()

    try:
        image_bytes = await garment_image.read()
        original_filename = garment_image.filename
        
        unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
        
        print(f"[*] Sending {original_filename} to Kaggle Qwen2-VL for analysis...")
        files = {"user_image": (original_filename, image_bytes, garment_image.content_type)}
        
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{kaggle_url}/digitize", 
                files=files,
                headers=KAGGLE_HEADERS
            )
            
            if response.status_code != 200:
                print(f"\n[-] NETWORK ERROR: Status {response.status_code}")
                raise HTTPException(status_code=500, detail=f"Kaggle Error: {response.status_code} - {response.text}")
            
            ai_metadata = response.json().get("metadata", {})

        file_path = os.path.join(WARDROBE_DIR, unique_filename)
        with open(file_path, "wb") as f:
            f.write(image_bytes)

        new_item = WardrobeItem(
            item_id=unique_filename, 
            category=ai_metadata.get("category", "unknown"),
            style=ai_metadata.get("style", "unknown"),
            color=ai_metadata.get("color", "unknown"),
            description=ai_metadata.get("description", "No description generated."),
            is_long=ai_metadata.get("is_long", False),
            user_id=current_user.id
        )
        
        db.add(new_item)
        db.commit()
        db.refresh(new_item)

        print(f"[+] Successfully added {unique_filename} to Digital Closet!")
        return {
            "status": "success", 
            "item_id": new_item.item_id,
            "extracted_data": ai_metadata
        }

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to Kaggle GPU. Is the notebook running with ngrok active?"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────
# WEEKLY PLAN GENERATION (LangGraph)
# ──────────────────────────────────────────────────────────────

from typing import Optional

@router.post("/generate-plan")
async def generate_plan(
    user_schedule: str = Form(...),
    user_avatar: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user)
):
    """Generate a 7-day outfit plan. Graph pauses before VTON rendering for human approval."""
    try:
        if user_avatar:
            avatar_filename = f"avatar_{uuid.uuid4().hex}_{user_avatar.filename}"
            avatar_path = os.path.join(WARDROBE_DIR, avatar_filename)
            
            image_bytes = await user_avatar.read()
            with open(avatar_path, "wb") as f:
                f.write(image_bytes)
        else:
            print("[*] No custom avatar uploaded. Using default avatar.")
            avatar_path = "default_avatar.jpg"
            if not os.path.exists(avatar_path):
                raise HTTPException(
                    status_code=400, 
                    detail="No custom avatar uploaded, and 'default_avatar.jpg' is missing from the server."
                )
            
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        
        initial_state = {
            "user_schedule": user_schedule,
            "avatar_path": avatar_path,
            "user_id": current_user.id
        }
        
        # Run graph until interrupt (pauses before VTON node)
        await fashion_agent.ainvoke(initial_state, config=config)
        
        # Get current state to return the generated plan
        state = fashion_agent.get_state(config)
        weekly_plan = state.values.get("weekly_plan")
        
        return {
            "status": "pending_approval",
            "thread_id": thread_id,
            "weekly_plan": weekly_plan
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ResumeRequest(BaseModel):
    thread_id: str
    approved: bool


async def run_vton_background(config: dict):
    """Helper function to run the LangGraph VTON node in the background."""
    try:
        await fashion_agent.ainvoke(None, config=config)
    except Exception as e:
        print(f"[-] Background VTON task failed: {e}")

@router.post("/resume-plan")
async def resume_plan(req: ResumeRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    """Resume the LangGraph after user approves/rejects the weekly plan (Runs in background)."""
    try:
        config = {"configurable": {"thread_id": req.thread_id}}
        state = fashion_agent.get_state(config)
        
        if not state.next:
            raise HTTPException(status_code=400, detail="Graph is not paused or already finished.")
            
        if req.approved:
            print(f"[+] Plan approved. Dispatching background VTON generation for thread: {req.thread_id}...")
            # Initialize job progress so the status endpoint works immediately
            vton_job_progress[req.thread_id] = {"status": "starting", "progress": 0, "total": 0, "images": []}
            
            # Dispatch to background
            background_tasks.add_task(run_vton_background, config)
            
            return {
                "status": "processing",
                "message": "VTON job started in the background. Poll /vton-status to check progress.",
                "thread_id": req.thread_id
            }
        else:
            print("[-] Plan rejected by user.")
            return {"status": "rejected", "message": "Plan was rejected. Please generate a new plan."}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/vton-status/{thread_id}")
async def get_vton_status(thread_id: str, current_user: User = Depends(get_current_user)):
    """Poll the status of a background VTON job."""
    progress = vton_job_progress.get(thread_id)
    if not progress:
        return {"status": "not_found", "message": "Job not found or not started."}
    return progress


# ──────────────────────────────────────────────────────────────
# VTON IMAGE SERVING
# ──────────────────────────────────────────────────────────────

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

@router.get("/vton/{filename}")
def get_vton_image(filename: str):
    """Serve a generated VTON composite image."""
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"VTON image '{filename}' not found.")
    return FileResponse(file_path, media_type="image/png")