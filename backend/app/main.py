from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.utils.rate_limiter import limiter
from app.utils.logger import logger
from app.routers import health, auth, diagnostic, practice, rag, dashboard, study_path, evaluation

settings = get_settings()

app = FastAPI(
    title="Path-Wise API Engine",
    description="Adaptive WAEC Study Tutor Backend Engine for Core Math & Elective Physics",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://path-wise.vercel.app",
    "https://*.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register All Core Routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(diagnostic.router)
app.include_router(practice.router)
app.include_router(rag.router)
app.include_router(dashboard.router)
app.include_router(study_path.router)
app.include_router(evaluation.router)


@app.on_event("startup")
async def startup_event():
    logger.info("Path-Wise FastAPI Engine initialized with AI RAG Evaluator, Study Path, & SUS Evaluation Engine.")


@app.get("/")
def root():
    return {"message": "Welcome to Path-Wise API Core"}