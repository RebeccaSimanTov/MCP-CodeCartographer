from mcp.server.fastmcp import FastMCP
import ast
import os
import networkx as nx
import matplotlib.pyplot as plt
import httpx
import json
from dotenv import load_dotenv
import sys
import io
import logging
import asyncio

# --- FIX FOR WINDOWS ENCODING (Must be at the top) ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
# -----------------------------------------------------

# טעינת משתני סביבה
load_dotenv()
logging.basicConfig(filename='server.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# --- Gemini API Config ---
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = "gemini-2.5-flash"
GENERATION_TEMPERATURE = 0.7
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# הגדרת השרת
mcp = FastMCP("Code Cartographer")

# משתנים גלובליים
dependency_graph = nx.DiGraph()

class ImportVisitor(ast.NodeVisitor):
    def __init__(self, current_file):
        self.current_file = current_file
        self.imports = []

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)

@mcp.tool()
def scan_repository(path: str = ".") -> str:
    """Scans Python files to build a dependency graph."""
    print(f"Scanning repository at path: {path}")
    global dependency_graph
    dependency_graph.clear()
    analyzed_files = 0
    target_path = path if path else "."

    for root, _, files in os.walk(target_path):
        for file in files:
            if file.endswith(".py") and file != "server.py":
                analyzed_files += 1
                full_path = os.path.join(root, file)
                module_name = file.replace(".py", "")
                
                dependency_graph.add_node(module_name, type="module")
                
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read())
                    visitor = ImportVisitor(module_name)
                    visitor.visit(tree)
                    for imp in visitor.imports:
                        imp_name = imp.split(".")[0]
                        dependency_graph.add_edge(module_name, imp_name)
                except Exception as e:
                    pass
                    logging.error(f"Error parsing {full_path}: {e}")

    if analyzed_files > 0:
        if len(dependency_graph.nodes) > 0:
            most_central = max(dict(dependency_graph.degree()).items(), key=lambda x: x[1])[0]
        else:
            most_central = "None"
    else:
        most_central = "None"

    return f"✅ Scan Complete. Analyzed {analyzed_files} files in '{target_path}'. Center node: '{most_central}'"

@mcp.tool()
def generate_architecture_map() -> str:
    """Generates a PNG graph of the architecture."""
    if dependency_graph.number_of_nodes() == 0:
        return "⚠️ Graph is empty. Please run 'scan_repository' first."

    plt.figure(figsize=(10, 8))
    pos = nx.spring_layout(dependency_graph, k=0.8)
    
    degrees = dict(dependency_graph.degree())
    node_sizes = [v * 500 + 1000 for v in degrees.values()]
    node_colors = [v for v in degrees.values()]

    nx.draw(dependency_graph, pos, with_labels=True, node_size=node_sizes, 
            node_color=node_colors, cmap=plt.cm.coolwarm, 
            font_size=10, font_weight="bold", edge_color="gray", arrows=True)
            
    plt.title("Codebase Architecture Map")
    filename = "architecture_map.png"
    plt.savefig(filename)
    plt.close()
    return f"🗺️ Map generated: {os.path.abspath(filename)}"


async def call_gemini(payload: dict) -> dict:
    """
    Calls the Gemini API with retries and SSL verification disabled.
    Based on working implementation from your project.
    """
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY")

    url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}"

    # --- SSL verification disabled for NetFree ---
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=False) as client:
        for attempt in range(MAX_RETRIES):
            try:
                logging.info(f"Attempt {attempt + 1}/{MAX_RETRIES} to call Gemini API...")
                
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                
                logging.info("Successfully received response from Gemini API")
                return resp.json()
                
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                response_text = e.response.text[:500]
                logging.error(f"HTTP Status Error on attempt {attempt + 1}: {status_code}")
                logging.error(f"Response body: {response_text}")

                
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(1.5 ** attempt)
                
            except httpx.TimeoutException as e:
                logging.error(f"Timeout on attempt {attempt + 1}: {e}")
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(1.5 ** attempt)
                
            except Exception as e:
                logging.error(f"Attempt {attempt + 1} failed: {e}", exc_info=True)
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(1.5 ** attempt)
                
    raise ConnectionError("Failed to connect to Gemini API after multiple retries")


@mcp.tool()
async def consult_ai_architect(module_name: str) -> str:
    """
    Uses Gemini API to analyze a module.
    Falls back to simulation if Gemini is unreachable.
    """
    return await _consult_ai_architect_async(module_name)

async def _consult_ai_architect_async(module_name: str) -> str:
    """Internal async implementation."""
    api_key = os.getenv("GEMINI_API_KEY")

    # בדיקה אם המודול קיים בגרף
    if module_name not in dependency_graph:
        return f"❌ Module '{module_name}' not found. Did you run scan_repository?"

    dependencies = list(dependency_graph.successors(module_name))
    used_by = list(dependency_graph.predecessors(module_name))

    if not api_key:
        logging.warning("No GEMINI_API_KEY set - returning simulated result")
        return _simulated_analysis(module_name, dependencies)

    prompt_text = f"""
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


    payload = {
        "contents": [{
            "parts": [{
                "text": prompt_text
            }]
        }],
        "generationConfig": {
            "temperature": GENERATION_TEMPERATURE,
            "maxOutputTokens": 10000
        }
    }

    try:
        data = await call_gemini(payload)
        
        parts = (
            data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
        )

        ai_text = " ".join(
            part.get("text", "") for part in parts if "text" in part
        ).strip()
        
        if not ai_text:
            logging.warning("Gemini returned empty text")
            return f"⚠️ Gemini responded but returned empty content.\n\n{_simulated_analysis(module_name, dependencies)}"
        
        return f"🤖 **Gemini AI Architect Analysis:**\n\n{ai_text}"
    
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        error_body = e.response.text[:500]
        
        logging.error(f"Gemini HTTP error {status}: {error_body}")
        
        error_msg = f"❌ Gemini API Error (HTTP {status})\n\nResponse:\n{error_body[:300]}"
        try:
            error_data = e.response.json()
            if 'error' in error_data:
                error_msg += f"\n\n💡 Error details: {error_data['error'].get('message', '')}"
        except:
            pass
        
        return f"{error_msg}\n\n{_simulated_analysis(module_name, dependencies)}"
    
    except httpx.TimeoutException:
        logging.error("Gemini request timed out")
        return f"⚠️ Request timed out.\n\n{_simulated_analysis(module_name, dependencies)}"
    
    except Exception as e:
        logging.exception("Gemini call failed")
        return f"⚠️ Error: {type(e).__name__}\n\n{_simulated_analysis(module_name, dependencies)}"


def _simulated_analysis(module_name: str, dependencies: list) -> str:
    """Fallback analysis when Gemini is unavailable."""
    role = "Core Orchestrator" if len(dependencies) > 2 else "Utility Helper"
    complexity = "High" if len(dependencies) > 2 else "Low"
    recommendation = "Consider decoupling logic." if len(dependencies) > 2 else "Keep as is."
    
    return f"""📊 **Static Analysis (Fallback Mode):**

Module: **{module_name}**
Role: **{role}**
Complexity Risk: **{complexity}**
Dependencies: {len(dependencies)}

**Recommendation:** {recommendation}

_(This is a rule-based analysis. For AI insights, ensure Gemini API is configured correctly.)_"""

if __name__ == "__main__":
    mcp.run()