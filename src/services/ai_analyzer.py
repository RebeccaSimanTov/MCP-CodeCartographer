import os
import logging
import httpx
import json
import asyncio
import networkx as nx
from dotenv import load_dotenv

class AIAnalyzer:
    """
    המוח המרכזי: מבצע 'MRI' לקוד.
    1. בודק 'בריאות' (Complexity/Risk) - לחישוב גודל וצבע הבועות.
    2. מוצא 'עורקים נסתרים' (Hidden Links) - לציור קווים מקווקווים.
    
    מותאם במיוחד לנטפרי (SSL Verification Disabled + Rate Limit Handling).
    """
    
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.api_base = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-2.5-flash"  # שם המודל המדויק והעדכני
        self.max_retries = 3
        
        # לוגינג מוצנע
        masked = "****" if self.api_key else "(not set)"
        logging.debug(f"AI Analyzer initialized. Key: {masked}")

    async def run_mri_scan(self, graph: nx.DiGraph):
        """
        מריץ את כל הניתוחים על הגרף ומחזיר את התוצאות המשולבות.
        """
        logging.info("🧠 AI is starting the holistic MRI Scan...")
        
        # 1. איסוף דגימות קוד מכל הקבצים בגרף
        files_data = {}
        for node, data in graph.nodes(data=True):
            path = data.get("file_path")
            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        files_data[node] = f.read(3000)
                except Exception as e:
                    logging.warning(f"Could not read {node}: {e}")

        if not files_data or not self.api_key:
            logging.warning("Skipping AI scan (No data or No API Key)")
            return {}, []

        # 2. הרצת שני הניתוחים
        risk_scores = await self._analyze_risk(files_data)
        hidden_links = await self._analyze_shadows(files_data)
        
        logging.info(f"MRI Scan Complete. Risks found: {len(risk_scores)}, Hidden links: {len(hidden_links)}")
        return risk_scores, hidden_links

    async def _analyze_risk(self, files_data: dict) -> dict:
        """מבקש מה-AI לדרג מורכבות קוד מ-1 עד 10."""
        prompt = f"""
        Analyze these Python modules. Rate their **Complexity & Maintainability** from 1 (Clean) to 10 (Critical Mess).
        
        Criteria for High Score (8-10):
        - Huge functions or classes.
        - Hardcoded values / Magic numbers.
        - Poor naming variables.
        - "Spaghetti code" logic.
        
        Modules Code Snippets:
        {json.dumps(files_data, indent=2)}
        
        Task:
        Return a strict JSON object: {{ "module_name": integer_score }}
        """
        return await self._call_gemini(prompt, default_val={})

    async def _analyze_shadows(self, files_data: dict) -> list:
        """מבקש מה-AI למצוא קשרים לוגיים שלא מופיעים באימפורטים."""
        prompt = f"""
        Find HIDDEN logical connections (Shadow Architecture) that are NOT explicit imports.
        Look for shared infrastructure usage:
        1. Shared Database Table names (e.g., both use "users_table").
        2. Shared Queue Topics / Redis Keys.
        3. API Calls (one defines route '/login', other requests '/login').
        
        Modules Code Snippets:
        {json.dumps(files_data, indent=2)}
        
        Task:
        Return a strict JSON list: 
        [ {{ "source": "module_A", "target": "module_B", "type": "Database/Queue/API" }} ]
        """
        return await self._call_gemini(prompt, default_val=[])

    async def _call_gemini(self, prompt: str, default_val):
        """
        פונקציית עזר לתקשורת עם גוגל.
        כולל טיפול מיוחד בשגיאות 429 (Too Many Requests).
        """
        url = f"{self.api_base}/models/{self.model}:generateContent?key={self.api_key}"
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            for attempt in range(self.max_retries):
                try:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text)
                
                except httpx.HTTPStatusError as e:
                    # טיפול בחסימת קצב (Rate Limit) - התיקון החשוב!
                    if e.response.status_code == 429:
                        logging.warning(f"⚠️ Hit Rate Limit (429). Cooling down for 10 seconds...")
                        await asyncio.sleep(10) # המתנה ארוכה כדי לתת ל-API להירגע
                    else:
                        logging.error(f"HTTP Error: {e}")
                        await asyncio.sleep(2)
                        
                except Exception as e:
                    logging.warning(f"AI Attempt {attempt+1} failed: {e}")
                    if attempt == self.max_retries - 1:
                        return default_val
                    await asyncio.sleep(2)
                    
        return default_val