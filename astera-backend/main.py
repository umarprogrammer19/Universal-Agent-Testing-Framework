"""
main.py
FastAPI application entry point
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

from routes.suites import router as suites_router
from routes.runs import router as runs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "=" * 60)
    print("UATF Backend Starting...")
    print("=" * 60)
    print(f"Server:   http://0.0.0.0:{os.getenv('PORT', 8000)}")
    print(f"API Docs: http://localhost:{os.getenv('PORT', 8000)}/docs")
    print(f"CORS:     {os.getenv('FRONTEND_URL', 'http://localhost:3000')}")
    print("=" * 60 + "\n")
    yield
    print("\nUATF Backend Shutting Down...\n")


app = FastAPI(
    title="UATF API",
    description="Universal Agent Testing Framework — Multi-Model Agent Testing",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(suites_router, prefix="/api", tags=["suites"])
app.include_router(runs_router, prefix="/api", tags=["runs"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "UATF API", "version": "3.0.0"}


@app.get("/")
async def root():
    return {"message": "UATF — Universal Agent Testing Framework", "docs": "/docs"}


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc), "status": "error"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", "True").lower() == "true",
        log_level="info",
    )
