import os
import json
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from PIL import Image
import google.generativeai as genai
from jose import JWTError, jwt
from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# Setup & Configuration
# ---------------------------------------------------------------------------
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "pocket_smart_secret_key_12345")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not found.")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

app = FastAPI(title="PocketSmart AI: Smart Budget Planner")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static/uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Mock In-Memory Databases
db_users: Dict[str, Dict[str, Any]] = {}
db_history: Dict[str, List[Dict[str, Any]]] = {}

# ---------------------------------------------------------------------------
# Auth Utilities
# ---------------------------------------------------------------------------
def verify_password(plain_pwd: str, hashed_pwd: str) -> bool:
    return pwd_context.verify(plain_pwd, hashed_pwd)

def get_password_hash(pwd: str) -> str:
    return pwd_context.hash(pwd)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username not in db_users:
            return None
        return db_users[username]
    except JWTError:
        return None

def extract_json_from_response(text: str) -> dict:
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text).strip()
    return json.loads(text)

# ---------------------------------------------------------------------------
# AI Utility Logic
# ---------------------------------------------------------------------------
def generate_home_recommendations(data: dict) -> dict:
    prompt = f"""
    You are an interior design budget planner. Allocate a budget of ₹{data['total_budget']} in INR for the following criteria:
    Lights: {data.get('num_lights', 0)}, Fans: {data.get('num_fans', 0)}, Furniture: {data.get('num_furniture', 0)}, Dining Tables: {data.get('num_dining_tables', 0)}.
    Rooms included: Living Room={data.get('has_living_room', False)}, Kitchen={data.get('has_kitchen', False)}, Bedroom={data.get('has_bedroom', False)}.
    Additional notes: {data.get('additional_requirements', '')}.

    Return ONLY a valid JSON object matching this structure:
    {{
        "total_budget": {data['total_budget']},
        "budget_breakdown": [
            {{
                "category": "Lighting",
                "allocation": 1500,
                "items": [
                    {{
                        "name": "LED Bulb",
                        "description": "Energy efficient bulbs",
                        "estimated_price": 300,
                        "quantity": 5,
                        "search_term": "LED Bulb Warm White"
                    }}
                ]
            }}
        ],
        "remaining_budget": 500,
        "additional_suggestions": ["Suggestion 1", "Suggestion 2"]
    }}
    """
    response = gemini_model.generate_content(prompt)
    result = extract_json_from_response(response.text)

    # Dynamic Shopping Link Injection
    for category in result.get("budget_breakdown", []):
        for item in category.get("items", []):
            st = urllib.parse.quote_plus(item.get("search_term", item.get("name", "")))
            item["shopping_links"] = {
                "Amazon": f"https://www.amazon.in/s?k={st}",
                "Flipkart": f"https://www.flipkart.com/search?q={st}",
                "IKEA": f"https://www.ikea.com/in/en/search/?q={st}",
                "Ajio": f"https://www.ajio.com/search/?text={st}"
            }
    return result

def generate_party_recommendations(data: dict) -> dict:
    prompt = f"""
    You are an AI Event Planner. Plan an event with budget ₹{data['total_budget']} INR for {data['num_guests']} guests.
    Event Type: {data['party_type']}, Venue Type: {data.get('venue_type', 'Any')}.
    Catering Required: {data.get('needs_catering', True)}, Decoration Required: {data.get('needs_decoration', True)}, Entertainment Required: {data.get('needs_entertainment', True)}.
    Notes: {data.get('additional_requirements', '')}.

    Return ONLY a valid JSON object matching this structure:
    {{
        "total_budget": {data['total_budget']},
        "budget_breakdown": [
            {{
                "category": "catering",
                "allocation": 5000,
                "items": [
                    {{
                        "name": "Party Food Package",
                        "item_details": "Buffet for guests",
                        "estimated_price": 4500,
                        "search_term": "Party Catering Service"
                    }}
                ]
            }}
        ],
        "remaining_budget": 500,
        "additional_suggestions": ["Suggestion 1"]
    }}
    """
    response = gemini_model.generate_content(prompt)
    result = extract_json_from_response(response.text)

    category_platform_map = {
        "venue": {"Google": "https://www.google.com/search?q={}", "OYO": "https://www.oyorooms.com/search?location={}"},
        "catering": {"Swiggy": "https://www.swiggy.com/search?query={}", "Zomato": "https://www.zomato.com/search?q={}"},
        "decoration": {"Amazon": "https://www.amazon.in/s?k={}", "Flipkart": "https://www.flipkart.com/search?q={}"},
        "entertainment": {"BookMyShow": "https://in.bookmyshow.com/search?q={}", "Amazon": "https://www.amazon.in/s?k={}"}
    }

    for category in result.get("budget_breakdown", []):
        cat_name = category.get("category", "").lower()
        platforms = category_platform_map.get(cat_name, {"Amazon": "https://www.amazon.in/s?k={}", "Flipkart": "https://www.flipkart.com/search?q={}"})
        for item in category.get("items", []):
            st = urllib.parse.quote_plus(item.get("search_term", item.get("name", "")))
            item["shopping_links"] = {plat: url.format(st) for plat, url in platforms.items()}
            
    return result

def generate_jewelry_recommendations(data: dict, image_path: Optional[str] = None) -> dict:
    base_prompt = f"""
    You are an AI Jewelry Recommendation Assistant.
    Provide jewelry suggestions for budget ₹{data['total_budget']} INR for occasion: {data['occasion']}.
    Style preferences: {data.get('preferences', 'Modern & Elegant')}.
    """
    
    if image_path and os.path.exists(image_path):
        prompt = base_prompt + "\nAnalyze the uploaded outfit image. Suggest jewelry matching color, neckline, and style."
        img = Image.open(image_path)
        response = gemini_model.generate_content([prompt, img])
    else:
        prompt = base_prompt + "\nFormat response as valid JSON."
        response = gemini_model.generate_content(prompt)

    prompt_schema = """
    Ensure response format strictly follows JSON:
    {
        "total_budget": 5000,
        "outfit_analysis": {"style": "Traditional", "color": "Red", "recommendation": "Gold-toned jewelry"},
        "jewelry_recommendations": [
            {
                "item_type": "Necklace",
                "description": "Kundan Choker Set",
                "style": "Ethnic",
                "estimated_price": 2500,
                "search_term": "Kundan Choker Necklace"
            }
        ],
        "remaining_budget": 500,
        "styling_tips": ["Match with gold bangles"]
    }
    """
    
    # Secondary validation request if non-json returned
    try:
        result = extract_json_from_response(response.text)
    except Exception:
        fallback = gemini_model.generate_content(f"Convert this to JSON format matching schema:\n{response.text}\nSchema:\n{prompt_schema}")
        result = extract_json_from_response(fallback.text)

    for item in result.get("jewelry_recommendations", []):
        st = urllib.parse.quote_plus(item.get("search_term", item.get("item_type", "")))
        item["shopping_links"] = {
            "Amazon": f"https://www.amazon.in/s?k={st}",
            "Flipkart": f"https://www.flipkart.com/search?q={st}",
            "BlueStone": f"https://www.bluestone.com/search?q={st}",
            "Tanishq": f"https://www.tanishq.co.in/search?q={st}"
        }

    return result

# ---------------------------------------------------------------------------
# Application Endpoints & Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register_user(username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if username in db_users:
        raise HTTPException(status_code=400, detail="Username already exists")
    db_users[username] = {
        "username": username,
        "email": email,
        "password": get_password_hash(password)
    }
    db_history[username] = []
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    user = db_users.get(username)
    if not user or not verify_password(password, user["password"]):
        return templates.TemplateResponse("login.html", {"request": None, "error": "Invalid username or password"})
    
    token = create_access_token({"sub": username})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    history = db_history.get(user["username"], [])
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "history": history})

# --- Planners ---
@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner_page(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("home_planner.html", {"request": request, "user": user})

@app.post("/generate-home")
async def generate_home(
    request: Request,
    total_budget: float = Form(...),
    num_lights: int = Form(0),
    num_fans: int = Form(0),
    num_furniture: int = Form(0),
    num_dining_tables: int = Form(0),
    has_living_room: bool = Form(False),
    has_kitchen: bool = Form(False),
    has_bedroom: bool = Form(False),
    additional_requirements: str = Form("")
):
    user = get_current_user(request)
    input_data = {
        "total_budget": total_budget,
        "num_lights": num_lights,
        "num_fans": num_fans,
        "num_furniture": num_furniture,
        "num_dining_tables": num_dining_tables,
        "has_living_room": has_living_room,
        "has_kitchen": has_kitchen,
        "has_bedroom": has_bedroom,
        "additional_requirements": additional_requirements
    }
    result = generate_home_recommendations(input_data)
    
    if user:
        db_history[user["username"]].append({
            "type": "Home Planner",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "budget": total_budget,
            "result": result
        })
        
    return templates.TemplateResponse("recommendations.html", {
        "request": request, "user": user, "title": "Home Interior Recommendations", "data": result
    })

@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner_page(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("party_planner.html", {"request": request, "user": user})

@app.post("/generate-party")
async def generate_party(
    request: Request,
    total_budget: float = Form(...),
    num_guests: int = Form(...),
    party_type: str = Form(...),
    venue_type: str = Form("Any"),
    needs_catering: bool = Form(True),
    needs_decoration: bool = Form(True),
    needs_entertainment: bool = Form(True),
    additional_requirements: str = Form("")
):
    user = get_current_user(request)
    input_data = {
        "total_budget": total_budget,
        "num_guests": num_guests,
        "party_type": party_type,
        "venue_type": venue_type,
        "needs_catering": needs_catering,
        "needs_decoration": needs_decoration,
        "needs_entertainment": needs_entertainment,
        "additional_requirements": additional_requirements
    }
    result = generate_party_recommendations(input_data)
    
    if user:
        db_history[user["username"]].append({
            "type": "Party Planner",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "budget": total_budget,
            "result": result
        })
        
    return templates.TemplateResponse("recommendations.html", {
        "request": request, "user": user, "title": "Party Budget Recommendations", "data": result
    })

@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner_page(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("jewelry_planner.html", {"request": request, "user": user})

@app.post("/generate-jewelry")
async def generate_jewelry(
    request: Request,
    total_budget: float = Form(...),
    occasion: str = Form(...),
    preferences: str = Form(""),
    outfit_image: Optional[UploadFile] = File(None)
):
    user = get_current_user(request)
    image_path = None
    if outfit_image and outfit_image.filename:
        image_path = f"static/uploads/{datetime.now().timestamp()}_{outfit_image.filename}"
        with open(image_path, "wb") as buffer:
            buffer.write(await outfit_image.read())

    input_data = {
        "total_budget": total_budget,
        "occasion": occasion,
        "preferences": preferences
    }
    result = generate_jewelry_recommendations(input_data, image_path)
    
    if user:
        db_history[user["username"]].append({
            "type": "Jewelry Planner",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "budget": total_budget,
            "result": result
        })
        
    return templates.TemplateResponse("recommendations.html", {
        "request": request, "user": user, "title": "Jewelry Recommendations", "data": result
    })

@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    user_history = db_history.get(user["username"], [])
    return templates.TemplateResponse("history.html", {"request": request, "user": user, "history": user_history})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
