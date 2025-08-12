import os
from fastapi import FastAPI, Request, Form, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import discord

# --- FastAPI App Setup ---
app = FastAPI()

# Mount the static files directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- Dependency for Authentication ---
async def get_current_user(request: Request):
    """
    Checks if a user is authenticated by looking for a session cookie.
    If not, it redirects them to the login page.
    """
    session_id = request.cookies.get("session_id")
    if session_id == os.getenv("DASHBOARD_SESSION_ID"):
        return session_id
    
    # If no valid session, redirect to login
    response = RedirectResponse(url="/login")
    raise HTTPException(status_code=303, detail="Redirecting to login")

# --- Routes ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serves the login page."""
    # Check if the user is already logged in, redirect if so
    session_id = request.cookies.get("session_id")
    if session_id == os.getenv("DASHBOARD_SESSION_ID"):
        return RedirectResponse(url="/")
        
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(response: Response, password: str = Form(...)):
    """Handles the login form submission."""
    if password == os.getenv("DASHBOARD_PASSWORD"):
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="session_id", value=os.getenv("DASHBOARD_SESSION_ID"), httponly=True)
        return response
    
    # Simple redirect back to login on failure
    raise HTTPException(status_code=303, detail="Incorrect password")

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def dashboard_page(request: Request):
    """Serves the main dashboard page."""
    bot = request.app.state.bot

    if not bot or not bot.is_ready():
        return templates.TemplateResponse("index.html", {"request": request, "bot_name": "Bot is starting..."})

    bot_name = bot.user.name
    guild_count = len(bot.guilds)
    latency_ms = round(bot.latency * 1000)
    server_name = bot.guilds[0].name if bot.guilds else "N/A"

    context = {
        "request": request,
        "bot_name": bot_name,
        "server_name": server_name,
        "guild_count": guild_count,
        "latency_ms": latency_ms,
    }
    return templates.TemplateResponse("index.html", context)


@app.get("/api/status", dependencies=[Depends(get_current_user)])
async def api_status(request: Request):
    """Provides live bot statistics as a JSON object."""
    bot = request.app.state.bot
    if bot and bot.is_ready():
        data = {
            "guild_count": len(bot.guilds),
            "latency_ms": round(bot.latency * 1000),
            "server_name": bot.guilds[0].name if bot.guilds else "N/A",
        }
        return data
    
    raise HTTPException(status_code=503, detail="Bot not ready")