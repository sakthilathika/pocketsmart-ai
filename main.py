import os
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from google import genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "pocketsmart_secret_key"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

users = {}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username in users and users[username] == password:
            session["user"] = username
            if "history" not in session:
                session["history"] = []
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        users[username] = password
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    history = session.get("history", [])
    return render_template("dashboard.html", username=session["user"], history=history)

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("history", None)
    return redirect(url_for("login"))

@app.route("/home_planner")
def home_planner():
    return render_template("home_planner.html")

@app.route("/jewelry_planner")
def jewelry_planner():
    return render_template("jewelry_planner.html")

@app.route("/party_planner")
def party_planner():
    return render_template("party_planner.html")

def clean_json_response(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text

def save_to_history(planner_type, title, budget):
    if "history" not in session:
        session["history"] = []
    history = session["history"]
    history.insert(0, {
        "type": planner_type,
        "title": title,
        "budget": budget
    })
    session["history"] = history

# 1. HOME INTERIOR PLANNER ROUTE
@app.route("/generate_home", methods=["POST"])
def generate_home():
    data = request.get_json() or {}
    rooms = data.get("rooms", "Living Room")
    budget = data.get("budget", "50000")
    
    prompt = f"""
    Act as a home interior budget planner. Plan interior for: {rooms} with budget: {budget}.
    Return ONLY valid JSON in this exact structure without markdown or backticks:
    {{
        "total_budget": "{budget}",
        "remaining_budget": "2000",
        "categories": [
            {{
                "name": "Furniture & Fixtures",
                "allocation": "30000",
                "items": [
                    {{"item": "Modular Sofa", "description": "Comfortable 3-seater sofa", "price": "18000", "quantity": 1}},
                    {{"item": "Center Coffee Table", "description": "Wooden coffee table with storage", "price": "7000", "quantity": 1}}
                ]
            }},
            {{
                "name": "Lighting & Decor",
                "allocation": "18000",
                "items": [
                    {{"item": "Warm LED Ceiling Lights", "description": "Energy-efficient ambient lighting set", "price": "5000", "quantity": 4}},
                    {{"item": "Wall Painting & Accents", "description": "Modern abstract canvas frame set", "price": "4000", "quantity": 2}}
                ]
            }}
        ]
    }}
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        cleaned_result = clean_json_response(response.text)
    except Exception as e:
        # Fallback response for demo safety if API fails or exhausts quota
        cleaned_result = json.dumps({
            "total_budget": budget,
            "remaining_budget": "2500",
            "categories": [
                {
                    "name": f"Furniture for {rooms}",
                    "allocation": str(int(float(budget)*0.6)),
                    "items": [
                        {"item": "Main Seating / Sofa", "description": "Ergonomic modern sofa set", "price": str(int(float(budget)*0.4)), "quantity": 1},
                        {"item": "Storage & Units", "description": "Multi-utility wooden cabinet unit", "price": str(int(float(budget)*0.2)), "quantity": 1}
                    ]
                },
                {
                    "name": "Lighting & Accessories",
                    "allocation": str(int(float(budget)*0.35)),
                    "items": [
                        {"item": "Ambient Pendant Lights", "description": "Designer warm ceiling fixtures", "price": str(int(float(budget)*0.15)), "quantity": 2},
                        {"item": "Decorative Wall Mirrors", "description": "Minimalist aesthetic frames", "price": str(int(float(budget)*0.15)), "quantity": 1}
                    ]
                }
            ]
        })
    
    save_to_history("Home Interior", f"Rooms: {rooms}", budget)
    return jsonify({"result": cleaned_result})

# 2. JEWELRY PLANNER ROUTE
@app.route("/generate_jewelry", methods=["POST"])
def generate_jewelry():
    data = request.get_json() or {}
    items = data.get("items", "Wedding")
    budget = data.get("budget", "25000")
    
    prompt = f"""
    Act as a jewelry budget planner. Plan jewelry for: {items} with total budget: {budget}.
    Return ONLY valid JSON in this exact structure without markdown or backticks:
    {{
        "total_budget": "{budget}",
        "outfit_analysis": {{
            "colors": "Gold / Diamond Accent",
            "style": "Elegant Festive / Bridal",
            "formality": "High"
        }},
        "recommendations": [
            {{
                "name": "22K Gold Plated Necklace Set",
                "description": "Traditional statement piece with matching earrings",
                "price": "15000",
                "style": "Traditional Elegant"
            }},
            {{
                "name": "Designer Bangle Pair",
                "description": "Intricate craftsmanship bangles suitable for grand occasions",
                "price": "8000",
                "style": "Classic"
            }}
        ],
        "tips": [
            "Keep metal tones uniform across all accessories.",
            "Choose lightweight jewelry for long events to ensure comfort."
        ]
    }}
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        cleaned_result = clean_json_response(response.text)
    except Exception as e:
        # Fallback response for demo safety
        cleaned_result = json.dumps({
            "total_budget": budget,
            "outfit_analysis": {
                "colors": "Gold & Silver Accents",
                "style": f"Custom Style for {items}",
                "formality": "High"
            },
            "recommendations": [
                {
                    "name": "Crafted Necklace & Earring Set",
                    "description": f"Designed specifically to complement your {items} budget",
                    "price": str(int(float(budget)*0.6)),
                    "style": "Premium Classic"
                },
                {
                    "name": "Matching Bracelet / Bangles",
                    "description": "Polished finish accessories for balanced aesthetic",
                    "price": str(int(float(budget)*0.35)),
                    "style": "Modern Minimalist"
                }
            ],
            "tips": [
                "Ensure color symmetry between your outfit and metallic tones.",
                "Balance heavier statement pieces with subtle wrists accessories."
            ]
        })

    save_to_history("Jewelry Planner", f"Occasion: {items}", budget)
    return jsonify({"result": cleaned_result})

# 3. PARTY PLANNER ROUTE
@app.route("/generate_party", methods=["POST"])
def generate_party():
    data = request.get_json() or {}
    event_type = data.get("event_type", "Birthday")
    guests = data.get("guests", "25")
    budget = data.get("budget", "15000")
    
    prompt = f"""
    Act as a party event planner. Plan a {event_type} party for {guests} guests with a budget of {budget}.
    Return ONLY valid JSON in this exact structure without markdown or backticks:
    {{
        "total_budget": "{budget}",
        "categories": [
            {{
                "name": "Venue & Decoration",
                "items": [
                    {{"name": "Banquet Hall Rental", "description": "AC Hall with seating setup", "price": "6000"}},
                    {{"name": "Theme Balloon & Floral Decor", "description": "Custom party backdrop and stage lighting", "price": "2500"}}
                ]
            }},
            {{
                "name": "Catering & Cake",
                "items": [
                    {{"name": "Buffet Meal Service", "description": f"Standard buffet spread for {guests} guests", "price": "5000"}},
                    {{"name": "Custom Theme Cake", "description": "2 kg custom design cake", "price": "1500"}}
                ]
            }}
        ]
    }}
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        cleaned_result = clean_json_response(response.text)
    except Exception as e:
        # Fallback response for demo safety
        cleaned_result = json.dumps({
            "total_budget": budget,
            "categories": [
                {
                    "name": "Venue & Ambience",
                    "items": [
                        {"name": "Space / Hall Rental", "description": f"Ideal capacity for {guests} guests", "price": str(int(float(budget)*0.4))},
                        {"name": "Stage & Lighting Setup", "description": "Theme decorations and lighting", "price": str(int(float(budget)*0.2))}
                    ]
                },
                {
                    "name": "Food & Entertainment",
                    "items": [
                        {"name": f"Buffet Catering ({guests} pax)", "description": "Full dinner menu with beverages", "price": str(int(float(budget)*0.3))},
                        {"name": "Sound & Music System", "description": "DJ unit and microphone setup", "price": str(int(float(budget)*0.1))}
                    ]
                }
            ]
        })

    save_to_history("Party Planner", f"{event_type} ({guests} Guests)", budget)
    return jsonify({"result": cleaned_result})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
