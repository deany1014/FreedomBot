import os
import sqlite3
import psutil
import asyncio
from typing import List, Dict, Any

from fastapi import FastAPI, Request, Form, Response, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import discord

# --- FastAPI App Setup ---
app = FastAPI()

# Mount the static files directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- Dependency for Authentication ---
# dashboard/app.py (New dependency for WebSockets)
async def get_websocket_user(websocket: WebSocket):
    session_id_from_url = websocket.query_params.get("session_id")
    if session_id_from_url == os.getenv("DASHBOARD_SESSION_ID"):
        return session_id_from_url
    
    await websocket.close(code=1008)
    raise WebSocketDisconnect("Invalid session ID in URL")

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
    raise HTTPException(status_code=303, detail="Redirecting to login", headers={"Location": "/login"})

# --- Authentication Routes ---

@app.get("/logout")
async def logout():
    """Logs the user out by clearing the session cookie."""
    response = RedirectResponse(url="/login")
    response.delete_cookie("session_id")
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serves the login page."""
    session_id = request.cookies.get("session_id")
    if session_id == os.getenv("DASHBOARD_SESSION_ID"):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("auth/login.html", {"request": request})

@app.post("/login")
async def login(password: str = Form(...)):
    """Handles the login form submission."""
    if password == os.getenv("DASHBOARD_PASSWORD"):
        redirect_response = RedirectResponse(url="/", status_code=303)
        redirect_response.set_cookie(key="session_id", value=os.getenv("DASHBOARD_SESSION_ID"), httponly=True)
        return redirect_response
    
    raise HTTPException(status_code=303, detail="Incorrect password", headers={"Location": "/login"})

@app.get("/api/session", dependencies=[Depends(get_current_user)])
async def get_session_id(request: Request):
    return JSONResponse(content={"session_id": request.cookies.get("session_id")})

# --- Dashboard and WebSocket Routes ---

# dashboard/app.py (Updated main dashboard route)
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def dashboard_page(request: Request):
    bot = request.app.state.bot
    
    if not bot or not bot.is_ready():
        return templates.TemplateResponse("index.html", {"request": request, "bot_name": "Bot is starting..."})
    
    bot_name = bot.user.name
    server_name = bot.guilds[0].name if bot.guilds else "N/A"
    
    # Pass the session ID to the template
    session_id = request.cookies.get("session_id")

    context = {
        "request": request,
        "bot_name": bot_name,
        "server_name": server_name,
        "session_id": session_id,  # <-- NEW: Pass the session ID here
    }
    return templates.TemplateResponse("index.html", context)

@app.websocket("/ws/stats")
async def websocket_endpoint(websocket: WebSocket, session_id: str = Depends(get_websocket_user)):
    """Provides real-time bot and server stats via WebSocket."""
    await websocket.accept()
    try:
        while True:
            # Gather bot and system stats
            bot = websocket.app.state.bot
            
            # Bot-specific stats
            bot_stats = {
                "guild_count": len(bot.guilds) if bot and bot.is_ready() else 0,
                "latency_ms": round(bot.latency * 1000) if bot and bot.is_ready() else "N/A",
                "user_count": len(bot.users) if bot and bot.is_ready() else 0,
                "channel_count": sum(len(g.channels) for g in bot.guilds) if bot and bot.is_ready() else 0,
            }

            # System-level stats using psutil
            system_stats = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                "ram_percent": psutil.virtual_memory().percent,
                "uptime_seconds": round(psutil.boot_time()),
                "network_io_sent_mb": round(psutil.net_io_counters().bytes_sent / (1024**2), 2),
                "network_io_recv_mb": round(psutil.net_io_counters().bytes_recv / (1024**2), 2),
            }

            stats_data = {"bot": bot_stats, "system": system_stats}

            # Send the JSON data to the connected client
            await websocket.send_json(stats_data)
            
            # Wait for a bit before sending the next update
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        print("Client disconnected.")

# --- Database Viewer Routes ---
DATABASE_DIR = os.path.join(BASE_DIR, "..", "database")

@app.get("/db", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def list_databases(request: Request):
    """Lists all available .db files in the database folder."""
    db_files = [f for f in os.listdir(DATABASE_DIR) if f.endswith(".db")]
    context = {"request": request, "db_files": db_files}
    return templates.TemplateResponse("viewer/db_list.html", context)

@app.get("/db/{db_name}", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def view_database_tables(request: Request, db_name: str):
    """Lists tables within a specific database file."""
    db_path = os.path.join(DATABASE_DIR, db_name)
    if not os.path.exists(db_path) or not db_path.endswith(".db"):
        raise HTTPException(status_code=404, detail="Database not found")

    tables: List[str] = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read database: {e}")
    finally:
        if conn:
            conn.close()

    context = {"request": request, "db_name": db_name, "tables": tables}
    return templates.TemplateResponse("viewer/db_tables.html", context)

@app.get("/db/{db_name}/{table_name}", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def view_table_data(
    request: Request,
    db_name: str,
    table_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """Displays paginated data from a specific table."""
    db_path = os.path.join(DATABASE_DIR, db_name)
    if not os.path.exists(db_path) or not db_path.endswith(".db"):
        raise HTTPException(status_code=404, detail="Database not found")

    offset = (page - 1) * page_size
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?;", (table_name,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Table not found")

        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        total_rows = cursor.fetchone()[0]

        cursor.execute(f"SELECT * FROM `{table_name}` LIMIT ? OFFSET ?", (page_size, offset))
        data = cursor.fetchall()
        
        columns = [col[0] for col in cursor.description]
        records = [dict(row) for row in data]
        total_pages = (total_rows + page_size - 1) // page_size
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read table data: {e}")
    finally:
        if conn:
            conn.close()

    context = {
        "request": request,
        "db_name": db_name,
        "table_name": table_name,
        "columns": columns,
        "records": records,
        "page": page,
        "page_size": page_size,
        "total_rows": total_rows,
        "total_pages": total_pages,
    }
    return templates.TemplateResponse("viewer/db_table_data.html", context)