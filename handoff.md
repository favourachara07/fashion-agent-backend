# Fashion Agent Backend - Handoff Document

## Overview
This repository contains a **FastAPI backend** for an AI-powered "Fashion Agent" that acts as a digital closet and personal stylist. The application integrates multiple AI services to manage a digital wardrobe, generate outfit plans using RAG, and orchestrate a workflow with a Human-in-the-Loop pause before rendering Virtual Try-On (VTON) images.

## Architecture & Core Technologies
- **Framework**: FastAPI (Python)
- **Authentication**: JWT Bearer Auth (Multi-Tenancy support) with Passlib & Bcrypt.
- **Database**: SQLite (managed via SQLAlchemy) for storing wardrobe metadata (including dynamic properties like `is_long` for sleeve/pant lengths).
- **RAG Database**: ChromaDB for storing and retrieving fashion trends and context.
- **External APIs**: 
  - Open-Meteo for live 7-day weather forecasting (Default: Lagos, Nigeria).
  - Kaggle GPU Microservice for Qwen2-VL (Metadata Extraction) and CatVTON (Virtual Try-On).
- **LLM/Agent Orchestration**: 
  - **LangGraph**: Manages the agent workflow (`context` -> `styling` -> `vton`).
  - **LangChain & Google Gemini 2.5 Flash**: Used as the core stylist agent to generate the 7-day wardrobe plan.
- **External GPU Compute (Kaggle Microservice)**:
  - Expects an external service running on Kaggle via ngrok (`KAGGLE_GPU_URL`).
  - Used for visual data extraction (Qwen2-VL) and VTON rendering.

## Directory Structure
- `app/main.py`: The FastAPI application entry point. Handles startup tasks like DB initialization and injecting mock trend data into the RAG system.
- `app/api/routes.py`: Defines all REST endpoints.
- `app/services/orchestrator.py`: Contains the `fashion_agent` LangGraph logic.
- `app/core/`: Contains the database setup (`database.py`) and RAG configuration (`rag_db.py`).
- `app/models/` & `app/schemas/`: SQLAlchemy models and Pydantic schemas.
- `uploaded_wardrobe/`: Local directory where uploaded garment images, user avatars, and generated VTON composite images are stored.
- `chroma_data/`: Persistent storage for ChromaDB.

## Key Features & Endpoints

### 1. Wardrobe Management
- **`GET /wardrobe`**: Lists all digitized clothing items saved in the SQLite database.
- **`GET /wardrobe/{item_id}/image`**: Serves the raw uploaded image file for a given garment.
- **`POST /add-wardrobe-item`**: Accepts a garment image, forwards it to the Kaggle GPU microservice (Qwen2-VL endpoint `/digitize`) for automated metadata extraction (category, style, color, description, and `is_long`), saves the image locally, and stores the metadata natively in SQLite.

### 2. AI Outfit Planner (LangGraph Workflow)
- **`POST /generate-plan`**: 
  - **Inputs**: User's schedule and avatar image.
  - **Process**: Starts the `fashion_agent` LangGraph. 
    1. **Context Node**: Fetches user's wardrobe from SQLite and fashion trends from the RAG system.
    2. **Styling Node**: Uses Gemini 2.5 Flash to create a structured 7-day outfit plan based on weather, schedule, wardrobe constraints, and trends.
  - **Output**: Pauses execution *before* the expensive VTON generation and returns the generated plan for user review.

### 3. Human-in-the-Loop & Virtual Try-On
- **`POST /resume-plan`**: 
  - **Inputs**: `thread_id` and an `approved` boolean.
  - **Process**: If approved, resumes the LangGraph and dispatches the **VTON Node** as a FastApi `BackgroundTask`.
  - **Output**: Instantly returns a `processing` status so the client isn't blocked.
- **`GET /vton-status/{thread_id}`**: 
  - **Output**: Real-time polling endpoint that returns background job progress (e.g., 2/7 images completed).
- **`GET /vton/{filename}`**: Serves the generated VTON composite images.

## Setup & Environment Requirements
1. **Environment Variables**:
   - `KAGGLE_GPU_URL`: The ngrok URL of the Kaggle notebook providing the `/digitize` and `/try-on` endpoints. If this is not set or invalid, VTON and garment digitization will fail.
   - Requires API keys for Google Gemini (and potentially others if configured in `.env`).
2. **Local Storage**: The app automatically manages the `uploaded_wardrobe` and `chroma_data` directories.
3. **Database**: SQLite (`fashion_agent.db`) is initialized automatically on startup.

## Next Steps & Known Limitations
- **Deployment**: The current SQLite database works great locally, but should be swapped for PostgreSQL if deployed in a serverless environment (e.g. Render/Vercel) to avoid data loss.
- **Frontend App**: Needs a dedicated React/Next.js frontend to interact with the API rather than relying on `test_complete_pipeline.py`.
- **Kaggle Dependency**: Error handling around the Kaggle microservice assumes it will time out or fail cleanly if not running, but requires a manual restart of the Kaggle notebook if the ngrok URL expires.
