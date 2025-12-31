import os
import logging
import httpx
import json
import asyncio
import networkx as nx
import ast
import re
from dotenv import load_dotenv

class AIAnalyzer:
    """
    The 'Brain' of the system: Performs an Architectural MRI scan.
    
    Capabilities:
    1. Smart Context Extraction: Reads only structurally significant code lines.
    2. Risk Analysis: Detects spaghetti code and complexity.
    3. Shadow Link Detection: Finds hidden logical dependencies (DB/API/Queue).
    
    Compatibility:
    - Optimized for restricted networks (NetFree) via SSL bypass.
    - Handles API Rate Limits (429) automatically.
    - includes 'Strict JSON' enforcement to prevent parsing errors.
    """
    
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.api_base = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-2.5-flash" 
        self.max_retries = 3
        
        masked = "****" if self.api_key else "(not set)"
        logging.debug(f"AI Analyzer initialized. Key: {masked}")

    async def run_mri_scan(self, graph: nx.DiGraph):
        logging.info("🧠 AI is starting the holistic MRI Scan (Smart Mode)...")
        
        # 1. Collect Code Snippets
        files_data = {}
        for node, data in graph.nodes(data=True):
            path = data.get("file_path")
            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        smart_content = self._extract_smart_context(content)
                        files_data[node] = smart_content
                except Exception as e:
                    logging.warning(f"Could not read file for node {node}: {e}")

        if not files_data or not self.api_key:
            logging.warning("Skipping AI scan (Missing GEMINI_API_KEY).")
            return {}, []

        # 2. Run AI Analyses
        risk_scores = await self._analyze_risk(files_data)
        hidden_links = await self._analyze_shadows(files_data)
        
        logging.info(f"MRI Scan Complete. Risks found: {len(risk_scores)}, Hidden links found: {len(hidden_links)}")
        return risk_scores, hidden_links

    def _extract_smart_context(self, content: str) -> str:
        """
        Extracts only relevant lines (Definitions, Imports, DB calls, etc.)
        """
        try:
            tree = ast.parse(content)
            important_lines = []
            
            doc = ast.get_docstring(tree)
            if doc: important_lines.append(f'"""{doc}"""')

            lines = content.splitlines()
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"): continue
                
                if stripped.startswith(("class ", "def ", "@")):
                    important_lines.append(line)
                elif stripped.startswith(("import ", "from ")):
                    important_lines.append(stripped)
                elif "=" in stripped and stripped.isupper():
                    important_lines.append(stripped)
                elif any(keyword in stripped for keyword in [
                    "execute(", "cursor", "Table", 
                    "request(", "get(", "post(", "http", "fetch", 
                    "emit(", "publish(", "celery", "redis", "kafka", "sqs",
                    "os.getenv", "config", "environ"
                ]):
                    important_lines.append(line)

            result = "\n".join(important_lines)
            return result[:4000]

        except Exception:
            return content[:2000] + "\n...[SNIPPED]...\n" + content[-1000:]

    async def _analyze_risk(self, files_data: dict) -> dict:
        prompt = f"""
        You are a **Strict Code Auditor**. Perform a Risk Assessment.
        
        ### 🎯 Scoring Rules (1-10):
        * **1-3:** Clean, simple, PEP8 compliant.
        * **4-7:** Moderate complexity, hardcoded values.
        * **8-10:** "God Class" (too many responsibilities), spaghetti logic, security risks.
        
        ### 🚫 Output Rules:
        1. Return ONLY valid JSON. No markdown formatting (```json).
        2. Format: {{ "module_name": integer_score }}
        
        ### 📂 Code Snippets:
        {json.dumps(files_data, indent=2)}
        """
        return await self._call_gemini(prompt, default_val={})

    async def _analyze_shadows(self, files_data: dict) -> list:
        # This prompt is hardened to reduce hallucinations
        prompt = f"""
        You are a **Sherlock Holmes of Architecture**. 
        Find **HIDDEN LOGICAL CONNECTIONS** (Shadow Dependencies) that are NOT defined via imports.
        
        ### ⚠️ STRICT RULES TO AVOID FALSE POSITIVES:
        1. **IGNORE** common variable names like "id", "data", "user", "result", "config".
        2. **IGNORE** standard library calls.
        3. **ONLY REPORT** if you see an EXACT string match for a resource identifier (e.g., table name, queue topic, specific URL path).
        4. If you are not 100% sure, **DO NOT** report it.
        
        ### 🎯 Targets to Hunt:
        * **Shared DB Tables:** e.g., `INSERT INTO orders_table` (in File A) vs `SELECT * FROM orders_table` (in File B).
        * **Shared Queues:** e.g., `redis.publish('new_signup')` vs `redis.subscribe('new_signup')`.
        * **API Calls:** e.g., `@app.route('/api/pay')` vs `requests.post('/api/pay')`.
        
        ### 🚫 Output Rules:
        1. Return ONLY valid JSON. No markdown (```json).
        2. Format: [ {{ "source": "A", "target": "B", "type": "Shared DB 'x' / API '/y'" }} ]
        
        ### 📂 Code Snippets:
        {json.dumps(files_data, indent=2)}
        """
        return await self._call_gemini(prompt, default_val=[])

    def _clean_json_text(self, text: str) -> str:
        """
        Cleans the AI response to ensure it's valid JSON.
        Removes Markdown fences like ```json and ```
        """
        # Remove ```json ... ```
        pattern = r"```json\s*(.*?)\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
        
        # Remove generic ``` ... ```
        pattern_generic = r"```\s*(.*?)\s*```"
        match_generic = re.search(pattern_generic, text, re.DOTALL)
        if match_generic:
            return match_generic.group(1)
            
        return text.strip()

    async def _call_gemini(self, prompt: str, default_val):
        url = f"{self.api_base}/models/{self.model}:generateContent?key={self.api_key}"
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json", # Force JSON from API side
                "temperature": 0.2 # Low temperature = More deterministic/Precise
            }
        }
        
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            for attempt in range(self.max_retries):
                try:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    
                    # --- CLEANING STEP ---
                    clean_text = self._clean_json_text(text)
                    
                    return json.loads(clean_text)
                
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        logging.warning(f"⚠️ Hit Rate Limit (429). Cooling down for 10 seconds...")
                        await asyncio.sleep(10)
                    elif e.response.status_code == 403:
                        logging.error(f"❌ Forbidden (403). Check API Key or Model Name.")
                        return default_val
                    else:
                        logging.error(f"HTTP Error: {e}")
                        await asyncio.sleep(2)
                        
                except Exception as e:
                    logging.warning(f"AI Attempt {attempt+1} failed: {e}")
                    if attempt == self.max_retries - 1:
                        return default_val
                    await asyncio.sleep(2)
                    
        return default_val