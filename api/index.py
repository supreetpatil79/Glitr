import sys
import logging
from pathlib import Path

# Add project root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from main import app
except Exception as err:
    logging.exception("Vercel Serverless Function import error: %s", err)
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="GlitrAI Fallback App")

    @app.get("/{path:path}")
    @app.post("/{path:path}")
    async def startup_error_handler(path: str = ""):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Serverless Startup Exception",
                "detail": str(err),
                "hint": "Check Vercel Environment Variables (DATABASE_URL, GROQ_API_KEY)"
            }
        )
