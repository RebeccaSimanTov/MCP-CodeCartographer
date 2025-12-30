import os
import logging
import httpx
import asyncio
import networkx as nx
from dotenv import load_dotenv
from ..models.schemas import AIAnalysis, ErrorModel


class AIConsultant:
    """שירות לניתוח מודולים באמצעות Gemini AI."""
    
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.api_base = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-2.5-flash"
        self.temperature = 0.7
        self.timeout = 30
        self.max_retries = 3
        # Avoid ever logging the raw API key; log only its presence masked with stars
        masked = "****" if self.api_key else "(not set)"
        logging.debug(f"Gemini API Key status: {masked}")
    
    async def analyze(self, module_name: str, graph: nx.DiGraph) -> AIAnalysis:
        """
        מנתח מודול ומחזיר המלצות AI.
        
        Args:
            module_name: שם המודול לניתוח
            graph: גרף התלויות
            
        Returns:
            AIAnalysis עם ניתוח המודול
        """
        logging.info(f"Analyzing module: {module_name}")
        
        # בדיקה אם המודול קיים בגרף
        if module_name not in graph:
            logging.warning(f"Module '{module_name}' not found in graph")
            return AIAnalysis(
                module=module_name,
                dependencies=[],
                used_by=[],
                analysis=f"Module '{module_name}' not found. Did you run scan_repository?",
                simulated=False,
                errors=[ErrorModel(message="Module not found")],
            )
        
        # איסוף מידע על המודול
        dependencies = list(graph.successors(module_name))
        used_by = list(graph.predecessors(module_name))
        
        # אם אין API key, מחזירים ניתוח סימולציה
        if not self.api_key:
            logging.warning("No GEMINI_API_KEY set - returning simulated result")
            return self._create_simulated_analysis(
                module_name, dependencies, used_by, "No API Key"
            )
        
        # קריאה ל-API
        try:
            analysis_text = await self._call_gemini_api(
                module_name, dependencies, used_by
            )
            
            logging.info(f"AI analysis completed for module: {module_name}")
            
            return AIAnalysis(
                module=module_name,
                dependencies=dependencies,
                used_by=used_by,
                analysis=analysis_text,
                simulated=False,
            )
        
        except Exception as e:
            logging.error(f"AI analysis failed for {module_name}: {e}", exc_info=True)
            simulated = self._create_simulated_analysis(
                module_name, dependencies, used_by, f"Error: {type(e).__name__}"
            )
            simulated.errors.append(ErrorModel(message=str(e)))
            return simulated
    
    async def _call_gemini_api(
        self, module_name: str, dependencies: list, used_by: list
    ) -> str:
        """מבצע קריאה ל-Gemini API עם retries."""
        url = f"{self.api_base}/models/{self.model}:generateContent?key={self.api_key}"

        prompt = self._build_prompt(module_name, dependencies, used_by)
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": 10000
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            for attempt in range(self.max_retries):
                try:
                    logging.info(f"Gemini API call attempt {attempt + 1}/{self.max_retries}")

                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()

                    data = resp.json()
                    return self._extract_text_from_response(data)

                except httpx.HTTPStatusError as e:
                    logging.error(
                        f"HTTP {e.response.status_code} on attempt {attempt + 1}: "
                        f"{e.response.text[:200]}"
                    )
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(1.5 ** attempt)

                except httpx.TimeoutException as e:
                    logging.error(f"Timeout on attempt {attempt + 1}: {e}")
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(1.5 ** attempt)

                except Exception as e:
                    logging.error(f"Attempt {attempt + 1} failed: {e}")
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(1.5 ** attempt)
        
        raise ConnectionError("Failed to connect to Gemini API after multiple retries")
    
    def _build_prompt(self, module_name: str, dependencies: list, used_by: list) -> str:
        """בונה את ה-prompt ל-AI."""
        return f"""
Analyze this Python module.

Module name: {module_name}
Imports: {', '.join(dependencies) if dependencies else 'None'}
Used by: {', '.join(used_by) if used_by else 'None'}

Rules:
- Write exactly 3 complete sentences.
- Do not write introductions or summaries.
- Do not use bullet points.
- Start immediately with the analysis.
"""
    
    def _extract_text_from_response(self, data: dict) -> str:
        """מחלץ את הטקסט מתשובת ה-API."""
        parts = (
            data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
        )
        
        ai_text = " ".join(
            part.get("text", "") for part in parts if "text" in part
        ).strip()
        
        if not ai_text:
            raise ValueError("Gemini returned empty text")
        
        return ai_text
    
    def _create_simulated_analysis(
        self, module_name: str, dependencies: list, used_by: list, note: str
    ) -> AIAnalysis:
        """יוצר ניתוח מבוסס כללים כ-fallback."""
        role = "Core Orchestrator" if len(dependencies) > 2 else "Utility Helper"
        complexity = "High" if len(dependencies) > 2 else "Low"
        recommendation = (
            "Consider decoupling logic." if len(dependencies) > 2 
            else "Keep as is."
        )
        
        analysis_text = (
            f"(SIMULATED) Module: {module_name}. "
            f"Role: {role}. "
            f"Complexity: {complexity}. "
            f"Recommendation: {recommendation}. "
            f"Note: {note}"
        )
        
        return AIAnalysis(
            module=module_name,
            dependencies=dependencies,
            used_by=used_by,
            analysis=analysis_text,
            simulated=True,
            meta={
                "role": role,
                "complexity": complexity,
                "recommendation": recommendation
            },
        )