import os
from dotenv import load_dotenv

# Load .env BEFORE any LangChain/Google imports
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.rag_db import rag_db
from app.core.database import Base, engine
from app.api.routes import router as api_router
from app.api.auth_routes import router as auth_router

MOCK_TRENDS = [
    {
        "style": "casual Y2K",
        "event": "party",
        "description": "Gen Z trend for casual parties: oversized vintage graphic tees, faded baggy denim jeans, and chunky sneakers."
    },
    {
        "style": "streetwear",
        "event": "hangout",
        "description": "Everyday streetwear: oversized hoodies layered over a basic tee, technical cargo pants, and sleek running sneakers."
    },
    {
        "style": "formal cultural",
        "event": "wedding or high-end event",
        "description": "Blending traditional attire for formal events: A vibrant traditional outfit with intricate embroidery, paired with sharp, tailored black dress trousers."
    }
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up: Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Starting up: Injecting mock data into RAG...")
    rag_db.populate(MOCK_TRENDS)
    yield
    print("Shutting down...")

app = FastAPI(title="Fashion Agent API", lifespan=lifespan)

# CORS middleware for mobile client access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the API router
app.include_router(auth_router, prefix="/auth")
app.include_router(api_router)

@app.get("/")
def health_check():
    kaggle_url = os.getenv("KAGGLE_GPU_URL", "NOT SET")
    return {
        "status": "Online",
        "database": "Connected",
        "kaggle_gpu_url": kaggle_url
    }