from mcp.server.fastmcp import FastMCP
import sys
import io
import os
import logging
import json

# --- Windows Encoding Fix ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Import Services
from src.services.repository_scanner import RepositoryScanner, MCP_STORAGE_DIR
from src.services.graph_generator import GraphGenerator
from src.services.ai_analyzer import AIAnalyzer
from src.models.schemas import ScanResult, MapResult

# Logging Configuration
logging.basicConfig(
    filename='server.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

# Initialize MCP Server
mcp = FastMCP("Code Cartographer")

# Initialize Tools
scanner = RepositoryScanner()
graph_gen = GraphGenerator()
ai_analyzer = AIAnalyzer()

# --- Helper: Load Graph & Metadata from Disk ---
def _load_graph_from_disk(graph_id: str):
    path = os.path.join(MCP_STORAGE_DIR, f"{graph_id}.json")
    if not os.path.exists(path):
        return None
    
    with open(path, "r", encoding="utf-8") as f: 
        data = json.load(f)
    
    import networkx as nx
    g = nx.DiGraph()
    # Reconstruct Nodes
    for n in data["nodes"]: 
        g.add_node(n["id"], **{k:v for k,v in n.items() if k!="id"})
    # Reconstruct Edges
    for u,v in data["edges"]: 
        g.add_edge(u,v, type="explicit") # Mark standard imports as 'explicit'
        
    return g, data

@mcp.tool()
def scan_repository(path: str = ".") -> ScanResult:
    """
    1. Scans the codebase.
    2. Builds the dependency graph.
    3. Returns a Graph ID for further analysis.
    """
    logging.info(f"🚀 Tool called: scan_repository with path={path}")
    return scanner.scan(path)

@mcp.tool()
def generate_quick_map(graph_id: str) -> MapResult:
    """
    🎨 VISUALIZER: Generates the architectural map PNG.
    
    Smart Behavior:
    - If 'run_architectural_mri' was run previously, this tool AUTOMATICALLY 
      detects the data and visualizes the Risk Heatmap & Shadow Links (Red/Orange bubbles).
    - If no MRI data exists, it renders a clean, structural map (Blue bubbles).
    """
    logging.info(f"⚡ Tool called: generate_quick_map (Graph: {graph_id})")
    
    loaded = _load_graph_from_disk(graph_id)
    if not loaded:
        return MapResult(success=False, message=f"Graph ID {graph_id} not found.")
    
    g, data = loaded
    
    # Check for cached AI insights to hydrate the map
    risk_scores = {}
    hidden_links = []
    
    if "ai_analysis" in data:
        logging.info("🎨 MRI data detected in cache. Generating Risk Heatmap...")
        cached = data["ai_analysis"]
        risk_scores = cached.get("risk_scores", {})
        hidden_links = cached.get("hidden_links", [])
        
        # Inject hidden links into the graph object temporarily for drawing
        # This creates the dashed red lines!
        count = 0
        for link in hidden_links:
            if link["source"] in g and link["target"] in g:
                g.add_edge(link["source"], link["target"], type="hidden")
                count += 1
        logging.info(f"   -> Added {count} hidden links to visualization.")
    else:
        logging.info("🎨 No MRI data found. Generating Standard Structural Map...")

    # Delegate to the renderer
    # If risk_scores is empty, it defaults to the Blue/Clean theme.
    return graph_gen.generate_mri_view(g, risk_scores=risk_scores)

@mcp.tool()
async def run_architectural_mri(graph_id: str, force_refresh: bool = False) -> MapResult:
    """
    🏥 ANALYZER: Performs the AI Risk Assessment & Shadow Link detection.
    
    Output:
    - Returns a TEXT REPORT highlighting top risks and hidden dependencies.
    - Saves results to cache (so 'generate_quick_map' can visualize them later).
    - NOTE: This tool does NOT generate an image itself.
    """
    logging.info(f"🏥 Tool called: run_architectural_mri (Graph: {graph_id}, Force: {force_refresh})")
    
    loaded = _load_graph_from_disk(graph_id)
    if not loaded:
        return MapResult(success=False, message=f"Graph ID {graph_id} not found.")
    
    g, data = loaded

    # --- Smart Caching Logic ---
    risk_scores = {}
    hidden_links = []
    
    if not force_refresh and "ai_analysis" in data:
        logging.info("🚀 Cache Hit! Using existing AI results.")
        cached = data["ai_analysis"]
        risk_scores = cached.get("risk_scores", {})
        hidden_links = cached.get("hidden_links", [])
    
    else:
        logging.info("🧠 Cache Miss. Initiating AI Analysis (Gemini)...")
        # Run the heavy AI processing
        risk_scores, hidden_links = await ai_analyzer.run_mri_scan(g)
        
        # Persist results to disk
        data["ai_analysis"] = {
            "risk_scores": risk_scores,
            "hidden_links": hidden_links
        }
        path = os.path.join(MCP_STORAGE_DIR, f"{graph_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logging.info("💾 AI results saved to cache.")

    # --- Generate Textual Report (Markdown) ---
    top_risks = sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    
    report = ["# 🏥 Architectural MRI Report\n"]
    
    # Section 1: Risks
    if top_risks:
        report.append("### 🚨 Critical Risk Hotspots:")
        for name, score in top_risks:
            report.append(f"1. **`{name}`** (Risk Score: {score}/10)")
    else:
        report.append("### ✅ System Health: Excellent. No high-risk modules found.")
    
    report.append("")
    
    # Section 2: Hidden Links
    if hidden_links:
        report.append(f"### 👻 Shadow Dependencies ({len(hidden_links)} found):")
        for link in hidden_links[:3]:
            report.append(f"- **{link['source']}** ➡️ **{link['target']}** (via {link.get('type', 'Unknown')})")
        if len(hidden_links) > 3:
            report.append(f"- ...and {len(hidden_links)-3} more.")
    else:
        report.append("### 👁️ Visibility: 100%. No hidden dependencies detected.")

    report.append("\n💡 **Next Step:** Run `generate_quick_map` to see the visualization.")

    return MapResult(
        success=True,
        message="\n".join(report),
        node_count=g.number_of_nodes(),
        edge_count=g.number_of_edges()
    )

if __name__ == "__main__":
    os.makedirs(MCP_STORAGE_DIR, exist_ok=True)
    mcp.run()