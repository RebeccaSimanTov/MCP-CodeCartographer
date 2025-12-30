from mcp.server.fastmcp import FastMCP
import sys
import io
import os
import logging
import json

# --- תיקון קידוד לווינדוס ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ייבוא השירותים
from src.services.repository_scanner import RepositoryScanner, MCP_STORAGE_DIR
from src.services.graph_generator import GraphGenerator
from src.services.ai_analyzer import AIAnalyzer
from src.models.schemas import ScanResult, MapResult

# הגדרת לוגים
logging.basicConfig(
    filename='server.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

# יצירת שרת ה-MCP
mcp = FastMCP("Code Cartographer")

# אתחול הכלים
scanner = RepositoryScanner()
graph_gen = GraphGenerator()
ai_analyzer = AIAnalyzer()

# --- פונקציית עזר לטעינת גרף ---
def _load_graph_from_disk(graph_id: str):
    path = os.path.join(MCP_STORAGE_DIR, f"{graph_id}.json")
    if not os.path.exists(path):
        return None
    
    with open(path, "r", encoding="utf-8") as f: 
        data = json.load(f)
    
    import networkx as nx
    g = nx.DiGraph()
    for n in data["nodes"]: 
        g.add_node(n["id"], **{k:v for k,v in n.items() if k!="id"})
    for u,v in data["edges"]: 
        g.add_edge(u,v, type="explicit") # ברירת מחדל לקשרים
        
    return g, data

@mcp.tool()
def scan_repository(path: str = ".") -> ScanResult:
    """
    1. Scans the codebase.
    2. Builds the dependency graph.
    3. Returns a Graph ID for the analysis step.
    """
    logging.info(f"🚀 Tool called: scan_repository with path={path}")
    return scanner.scan(path)

@mcp.tool()
def generate_quick_map(graph_id: str) -> MapResult:
    """
    ⚡ FAST MODE: Generates the visual map WITHOUT AI analysis.
    Useful for quickly checking the folder structure and connections 
    before running the heavy MRI scan.
    """
    logging.info(f"⚡ Tool called: generate_quick_map (Graph: {graph_id})")
    
    loaded = _load_graph_from_disk(graph_id)
    if not loaded:
        return MapResult(success=False, message=f"Graph ID {graph_id} not found.")
    
    g, _ = loaded
    
    # שליחה לצייר ללא ציוני סיכון (הכל יהיה כחול ונקי)
    return graph_gen.generate(g, risk_scores={}, return_image=True)

@mcp.tool()
async def run_architectural_mri(graph_id: str, force_refresh: bool = False) -> MapResult:
    """
    🏥 THE WOW TOOL: Performs a full 'Architectural MRI'.
    Returns a visual map AND a textual risk analysis report.
    
    Visualizes:
    1. 📂 Clusters (Folders)
    2. 💣 Risk Heatmap (Red Bubbles)
    3. 👻 Shadow Links (Hidden Connections)
    """
    logging.info(f"🏥 Tool called: run_architectural_mri (Graph: {graph_id}, Force: {force_refresh})")
    
    loaded = _load_graph_from_disk(graph_id)
    if not loaded:
        return MapResult(success=False, message=f"Graph ID {graph_id} not found.")
    
    g, data = loaded

    # --- מנגנון הקאש החכם ---
    risk_scores = {}
    hidden_links = []
    
    if not force_refresh and "ai_analysis" in data:
        logging.info("🚀 Cache Hit! Using saved AI results.")
        cached = data["ai_analysis"]
        risk_scores = cached.get("risk_scores", {})
        hidden_links = cached.get("hidden_links", [])
    
    else:
        logging.info("🧠 Cache Miss. Running AI Analysis...")
        risk_scores, hidden_links = await ai_analyzer.run_mri_scan(g)
        
        # שמירה לקאש
        data["ai_analysis"] = {
            "risk_scores": risk_scores,
            "hidden_links": hidden_links
        }
        path = os.path.join(MCP_STORAGE_DIR, f"{graph_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # --- הוספת הנסתרות לגרף (לצורך הציור) ---
    for link in hidden_links:
        if link["source"] in g and link["target"] in g:
            g.add_edge(link["source"], link["target"], type="hidden")

    # --- יצירת דוח טקסטואלי (The Analysis) ---
    # מציאת 3 הקבצים המסוכנים ביותר
    top_risks = sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    
    report = ["# 🏥 MRI Analysis Report\n"]
    
    if top_risks:
        report.append("### 🚨 Top 3 Risk Hotspots:")
        for name, score in top_risks:
            report.append(f"1. **`{name}`** (Risk Score: {score}/10) - Needs Refactoring.")
    else:
        report.append("### ✅ System Health: Excellent. No high-risk modules detected.")
    
    report.append("")
    
    if hidden_links:
        report.append(f"### 👻 Shadow Architecture Detected ({len(hidden_links)} hidden links):")
        for link in hidden_links[:3]: # מציג רק 3 ראשונים כדי לא להעמיס
            report.append(f"- **{link['source']}** ➡️ **{link['target']}** (via {link.get('type', 'Unknown')})")
        if len(hidden_links) > 3:
            report.append(f"- ...and {len(hidden_links)-3} more.")
    else:
        report.append("### 👁️ No hidden dependencies found. Architecture is explicit.")

    report_text = "\n".join(report)

    # --- יצירת המפה ---
    result = graph_gen.generate_mri_view(g, risk_scores)
    
    # הזרקת הדוח לתוך הודעת התשובה
    result.message = report_text
    
    return result

if __name__ == "__main__":
    os.makedirs(MCP_STORAGE_DIR, exist_ok=True)
    mcp.run()