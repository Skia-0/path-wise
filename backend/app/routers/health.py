from fastapi import APIRouter
from app.db.supabase_client import supabase_admin
from app.utils.logger import logger

router = APIRouter(tags=["Health"])

@router.get("/health")
def health_check():
    db_status = "healthy"
    try:
        # Lightweight ping against canonical_topics table
        res = supabase_admin.table("canonical_topics").select("id").limit(1).execute()
    except Exception as e:
        logger.error(f"Healthcheck DB ping failed: {str(e)}")
        db_status = "unhealthy"

    return {
        "status": "online",
        "app": "Path-Wise API Engine",
        "database": db_status
    }