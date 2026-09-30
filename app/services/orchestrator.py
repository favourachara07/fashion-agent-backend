import httpx
import json
import os
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.database import SessionLocal
from app.models.wardrobe import WardrobeItem
from app.schemas.weekly_plan import WeeklyWardrobePlan
from app.core.rag_db import rag_db
from app.services.weather import get_weekly_weather
from contextlib import ExitStack

KAGGLE_HEADERS = {"ngrok-skip-browser-warning": "true"}


class FashionState(TypedDict):
    user_schedule: str
    weather_data: str
    avatar_path: str
    user_id: int
    wardrobe_items: List[Dict[str, Any]]
    trend_context: str  # RAG-retrieved fashion trend context
    weekly_plan: dict
    vton_image_paths: List[str]


async def context_node(state: FashionState):
    """Gather all context: wardrobe from SQLite + fashion trends from RAG."""
    print("-> [Context Node] Gathering wardrobe and trend data...")
    
    # 1. Load wardrobe from SQLite for the specific user
    user_id = state.get("user_id")
    db = SessionLocal()
    try:
        saved_items = db.query(WardrobeItem).filter(WardrobeItem.user_id == user_id).all() if user_id else db.query(WardrobeItem).all()
        db_wardrobe = [
            {
                "item_id": item.item_id,
                "category": item.category,
                "style": item.style,
                "color": item.color,
                "description": item.description,
                "is_long": getattr(item, "is_long", False)
            } for item in saved_items
        ]
    finally:
        db.close()
    
    # 2. Retrieve relevant fashion trends from ChromaDB RAG
    schedule = state.get("user_schedule") or "Monday: Office, Tuesday: Gym, Wednesday: Date night, Thursday: WFH, Friday: Party, Saturday: Casual outing, Sunday: Rest"
    
    # Use real Open-Meteo weather API for Lagos, Nigeria if not provided
    weather = state.get("weather_data")
    if not weather:
        print("   [+] Fetching live 7-day weather forecast for Lagos, Nigeria...")
        weather = get_weekly_weather(lat=6.45, lon=3.40, timezone="Africa/Lagos")

    trend_docs = rag_db.retrieve(schedule, n_results=2)
    trend_context = "\n".join(trend_docs) if trend_docs else "No specific trend data available."
    print(f"   [+] Found {len(db_wardrobe)} wardrobe items and {len(trend_docs)} trend references.")

    return {
        "wardrobe_items": db_wardrobe,
        "user_schedule": schedule,
        "weather_data": weather,
        "trend_context": trend_context
    }


async def styling_agent_node(state: FashionState):
    """Use Gemini to generate a 7-day outfit plan with RAG context."""
    print("-> [Styling Node] Generating 7-day plan with Gemini 2.0 Flash...")
    db_wardrobe = state.get("wardrobe_items", [])
    trend_context = state.get("trend_context", "No trend data available.")
    
    if not db_wardrobe:
        print("[-] Warning: Database is empty. Cannot make a recommendation.")
        return {"weekly_plan": {"plan": []}}
    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.5)
    structured_llm = llm.with_structured_output(WeeklyWardrobePlan)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are an expert AI fashion stylist. Your task is to plan a 7-day weekly wardrobe for the user.\n"
         "RULES:\n"
         "1. ONLY select 'item_id's that exist EXACTLY as written in the provided wardrobe list. Do NOT invent or modify item_id values.\n"
         "2. Repetition Penalty: Do not assign the same 'item_id' more than twice in the entire 7-day plan.\n"
         "3. If a bottom is not needed or none is available, output 'none' for bottom_id.\n"
         "4. Use the fashion trend insights below to inform your styling decisions.\n"
         "5. Consider the weather forecast when selecting outfits.\n\n"
         "FASHION TREND INSIGHTS:\n{trends}"),
        ("user", 
         "User Schedule:\n{schedule}\n\n"
         "Weather Forecast:\n{weather}\n\n"
         "Available Wardrobe (use EXACT item_id values from this list):\n{wardrobe}")
    ])
    
    chain = prompt | structured_llm
    
    result = await chain.ainvoke({
        "schedule": state["user_schedule"],
        "weather": state["weather_data"],
        "wardrobe": json.dumps(db_wardrobe, indent=2),
        "trends": trend_context
    })
    
    return {"weekly_plan": result.dict()}


# Global dictionary to track VTON progress for polling
vton_job_progress = {}

async def vton_dispatcher_node(state: FashionState, config: RunnableConfig):
    """Dispatch VTON requests to the Kaggle GPU microservice."""
    print("-> [VTON Node] Dispatching VTON requests to Kaggle...")
    
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    
    kaggle_url = os.getenv("KAGGLE_GPU_URL", "").rstrip("/")
    if not kaggle_url:
        print("[-] KAGGLE_GPU_URL not set. Skipping VTON generation.")
        vton_job_progress[thread_id] = {"status": "error", "progress": 0, "total": 0, "images": [], "error": "KAGGLE_GPU_URL not set"}
        return {"vton_image_paths": []}
    
    plan = state.get("weekly_plan", {}).get("plan", [])
    avatar_path = state.get("avatar_path")
    
    # Initialize job progress
    total_items = sum(1 for d in plan if d.get("top_id") and d.get("top_id") != "none")
    vton_job_progress[thread_id] = {
        "status": "processing",
        "progress": 0,
        "total": total_items,
        "images": []
    }
    
    if not avatar_path or not os.path.exists(avatar_path):
        print("[-] Avatar not found.")
        return {"vton_image_paths": []}
        
    generated_paths = []
    
    # Increased timeout to 400.0s to allow sequential rendering of both top and bottom on Kaggle
    async with httpx.AsyncClient(timeout=400.0) as client:
        for day_outfit in plan:
            top_id = day_outfit.get("top_id")
            bottom_id = day_outfit.get("bottom_id")
            
            if top_id and top_id != "none":
                top_path = os.path.join("uploaded_wardrobe", top_id)
                bottom_path = os.path.join("uploaded_wardrobe", bottom_id) if bottom_id and bottom_id != "none" else None
                
                if os.path.exists(top_path):
                    day_name = day_outfit.get("day", "unknown")
                    print(f"   [+] Synthesizing VTON for {day_name} using {top_id}...")
                    
                    try:
                        # ExitStack safely manages multiple file closures natively
                        with ExitStack() as stack:
                            avatar_file = stack.enter_context(open(avatar_path, "rb"))
                            top_file = stack.enter_context(open(top_path, "rb"))
                            
                            top_item = next((item for item in state.get("wardrobe_items", []) if item["item_id"] == top_id), None)
                            top_is_long = top_item.get("is_long", False) if top_item else False
                            
                            # Changed "garment_image" to "top_garment" to match the new Kaggle endpoint
                            files = [
                                ("user_avatar", ("avatar.jpg", avatar_file, "image/jpeg")),
                                ("top_garment", (top_id, top_file, "image/jpeg"))
                            ]
                            
                            data = {
                                "top_is_long": str(top_is_long).lower()
                            }
                            
                            # Dynamically attach the bottom garment if it exists in the schedule and on disk
                            if bottom_path and os.path.exists(bottom_path):
                                bottom_item = next((item for item in state.get("wardrobe_items", []) if item["item_id"] == bottom_id), None)
                                bottom_is_long = bottom_item.get("is_long", False) if bottom_item else False
                                
                                bottom_file = stack.enter_context(open(bottom_path, "rb"))
                                files.append(("bottom_garment", (bottom_id, bottom_file, "image/jpeg")))
                                data["bottom_is_long"] = str(bottom_is_long).lower()
                                print(f"       -> Including bottom garment: {bottom_id} (Long: {bottom_is_long})")
                            
                            response = await client.post(
                                f"{kaggle_url}/try-on",
                                files=files,
                                data=data,
                                headers=KAGGLE_HEADERS
                            )
                            
                            if response.status_code == 200:
                                vton_filename = f"vton_{day_name}_{top_id}.png"
                                vton_dir = "output"
                                os.makedirs(vton_dir, exist_ok=True)
                                vton_path = os.path.join(vton_dir, vton_filename)
                                with open(vton_path, "wb") as f:
                                    f.write(response.content)
                                generated_paths.append(vton_filename)
                                vton_job_progress[thread_id]["images"].append(vton_filename)
                                print(f"   [+] Saved: {vton_filename}")
                            else:
                                print(f"   [-] VTON failed for {top_id}: {response.status_code} - {response.text[:200]}")
                                
                            vton_job_progress[thread_id]["progress"] += 1
                                
                    except httpx.ConnectError:
                        print(f"   [-] Cannot connect to Kaggle GPU for {top_id}. Is the notebook running?")
                    except Exception as e:
                        print(f"   [-] Error during VTON for {top_id}: {str(e)}")
                else:
                    print(f"   [-] Garment {top_id} not found locally at {top_path}")
                    vton_job_progress[thread_id]["progress"] += 1
                    
    vton_job_progress[thread_id]["status"] = "completed"
    return {"vton_image_paths": generated_paths}


# Build the LangGraph
memory = MemorySaver()
builder = StateGraph(FashionState)
builder.add_node("context", context_node)
builder.add_node("styling", styling_agent_node)
builder.add_node("vton", vton_dispatcher_node)

builder.add_edge(START, "context")
builder.add_edge("context", "styling")
builder.add_edge("styling", "vton")
builder.add_edge("vton", END)

# Compile with interrupt before VTON node for human-in-the-loop approval
fashion_agent = builder.compile(checkpointer=memory, interrupt_before=["vton"])