import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from google import genai

app = FastAPI(title="PocketSmart AI")

# Serve static files for frontend UI
app.mount("/static", StaticFiles(directory="static"), name="static")

# Get Gemini API key from environment variable
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

class BudgetRequest(BaseModel):
    category: str  # e.g., Home Interior, Event Planning, Electronics, Jewelry
    total_budget: float
    items_needed: str  # e.g., Dining table, Ceiling fan, Lights

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/recommend")
def get_recommendation(data: BudgetRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set.")
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
        You are PocketSmart AI, an intelligent budget planner and recommendation assistant.
        
        Category: {data.category}
        Total Budget: ₹{data.total_budget}
        Items Needed: {data.items_needed}
        
        Provide a smart budget breakdown and curated product/service recommendations 
        across popular Indian platforms like Amazon, Flipkart, IKEA, Swiggy, Zomato, or OYO (where appropriate).
        Ensure the allocation fits strictly within the specified budget.
        
        Format the output clearly using Markdown with sections:
        1. Budget Allocation Summary
        2. Recommended Items & Estimated Prices
        3. Savings / Pro Tips
        """
        
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        
        return {"success": True, "recommendation": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
