# dashboard/app.py

import os
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
# You may need to import discord if you want type hinting for the bot object
import discord 

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Retrieve the bot instance from the app's state
    bot = request.app.state.bot

    # You can now access any bot attribute!
    # Let's prepare some data for the template.
    # We add a check to make sure the bot is fully ready before we try to access its properties.
    if not bot or not bot.is_ready():
        return templates.TemplateResponse("index.html", {"request": request, "bot_name": "Bot is starting..."})

    # Get live data from the bot
    bot_name = bot.user.name
    bot_id = bot.user.id
    guild_count = len(bot.guilds)
    latency_ms = round(bot.latency * 1000)

    # You can pass this data directly to your template
    context = {
        "request": request,
        "bot_name": bot_name,
        "bot_id": bot_id,
        "guild_count": guild_count,
        "latency_ms": latency_ms,
    }
    return templates.TemplateResponse("index.html", context)

@app.get("/api/status")
async def api_status(request: Request):
    """Provides live bot statistics as a JSON object."""
    try:
        bot = request.app.state.bot
        if bot and bot.is_ready():
            # If the bot is ready, return its live data
            data = {
                "guild_count": len(bot.guilds),
                "latency_ms": round(bot.latency * 1000),
            }
            return JSONResponse(content=data)
    except AttributeError:
        # This handles the case where the bot isn't ready or attached yet
        pass
    
    # If bot is not ready, return an error or placeholder status
    return JSONResponse(content={"error": "Bot not ready"}, status_code=503)