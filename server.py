from mcp.server.fastmcp import FastMCP
import sys
import io
import logging
import json
import networkx as nx

# --- Windows Encoding Fix ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Import Services
from src.services.repository_scanner import RepositoryScanner
from src.services.graph_generator import GraphGenerator
from src.services.ai_analyzer import AIAnalyzer
from src.services.storage_manager import storage  # <-- The new Boss
from src.models.schemas import ScanResult, MapResult, AIAnalysis, ErrorModel

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

# --- Helper: Load Graph & Metadata via Storage ---
def _load_graph(graph_id: str):
    """Loads graph data from storage and reconstructs NetworkX object."""
    data = storage.load_graph(graph_id)
    if not data:
        return None, None
    
    g = nx.DiGraph()
    # Reconstruct Nodes
    for n in data["nodes"]: 
        g.add_node(n["id"], **{k:v for k,v in n.items() if k!="id"})
    # Reconstruct Edges
    for u,v in data["edges"]: 
        g.add_edge(u,v, type="explicit") # Mark standard imports as 'explicit'
        
    return g, data

# ---------------------------------------------------------
# 🛠️ TOOLS
# ---------------------------------------------------------

@mcp.tool()
def scan_repository(path: str = ".") -> ScanResult:
    """
    Performs a comprehensive static analysis scan of a local Python repository.
    
    This tool parses the Abstract Syntax Tree (AST) of Python files to identify 
    modules, classes, and explicit import dependencies. It constructs a directed 
    dependency graph and persists it to the internal storage.

    Args:
        path (str): The absolute or relative file system path to the project root. 
                    Defaults to the current working directory.

    Returns:
        ScanResult: A structured object containing:
            - `graph_id` (str): The unique UUID required to reference this graph in other tools.
            - `analyzed_files` (int): Count of processed Python files.
            - `most_central` (str): The module with the highest degree centrality.
            - `success` (bool): Operation status.
    """
    logging.info(f"🚀 Tool called: scan_repository with path={path}")
    # The scanner now uses 'storage' internally to save the file
    return scanner.scan(path)

@mcp.tool()
def generate_quick_map(graph_id: str) -> MapResult:
    """
    Renders the current state of the architecture graph into a high-resolution visualization.
    
    This tool dynamically determines the visual style based on available data:
    1. **Structural Mode:** If only `scan_repository` has run, it generates a blue-themed 
       hierarchical map showing explicit dependencies.
    2. **MRI Mode:** If `run_architectural_mri` has populated the cache, it overlays a 
       Risk Heatmap (Red nodes for complexity) and visualizes Shadow Links (Dashed lines).

    Args:
        graph_id (str): The unique identifier obtained from `scan_repository`.

    Returns:
        MapResult: A structured object containing:
            - `image_path` (str): The local file path to the generated PNG image.
            - `node_count` (int): Total nodes rendered.
            - `edge_count` (int): Total edges rendered.
            - `success` (bool): Rendering status.
    """
    logging.info(f"⚡ Tool called: generate_quick_map (Graph: {graph_id})")
    
    g, data = _load_graph(graph_id)
    if not g:
        return MapResult(success=False, message=f"Graph ID {graph_id} not found.")
    
    # Check for cached AI insights
    risk_scores = {}
    hidden_links = []
    
    if "ai_analysis" in data:
        logging.info("🎨 MRI data detected in cache. Generating Risk Heatmap...")
        cached = data["ai_analysis"]
        risk_scores = cached.get("risk_scores", {})
        hidden_links = cached.get("hidden_links", [])
        
        # Inject hidden links for visualization
        count = 0
        for link in hidden_links:
            if link["source"] in g and link["target"] in g:
                g.add_edge(link["source"], link["target"], type="hidden")
                count += 1
        logging.info(f"   -> Added {count} hidden links to visualization.")
    else:
        logging.info("🎨 No MRI data found. Generating Standard Structural Map...")

    # Generate Image (GraphGenerator will persist the image and return path)
    result = graph_gen.generate_mri_view(g, risk_scores=risk_scores, graph_id=graph_id)
    if result.success and result.image_path:
        logging.info(f"Saved image to {result.image_path}")

    return result

@mcp.tool()
async def run_architectural_mri(graph_id: str, force_refresh: bool = False) -> AIAnalysis:
    """
    Executes a semantic AI analysis ("MRI") on the dependency graph to detect architectural risks.
    
    This tool utilizes an LLM (Gemini) to identify:
    1. **Shadow Dependencies:** Logical connections not explicitly imported (e.g., shared DB tables, API routes, Pub/Sub topics).
    2. **Code Complexity:** Assigns risk scores (1-10) to modules based on responsibility overload ("God Classes").
    
    Results are persisted to the graph's metadata storage to enrich future visualizations.

    Args:
        graph_id (str): The unique identifier obtained from `scan_repository`.
        force_refresh (bool): If True, bypasses the storage cache and forces a fresh AI inference.

    Returns:
        AIAnalysis: A structured analysis object containing:
            - `analysis` (str): A detailed Markdown report summarizing top risks and hidden links.
            - `module` (str): The name of the most central module analyzed.
            - `dependencies` (List[str]): Outgoing dependencies of the central module.
            - `used_by` (List[str]): Incoming dependencies to the central module.
    """
    logging.info(f"🏥 Tool called: run_architectural_mri (Graph: {graph_id}, Force: {force_refresh})")
    
    g, data = _load_graph(graph_id)
    if not g:
        # Return a minimal AIAnalysis with an error message
        err = ErrorModel(code="not_found", message=f"Graph ID {graph_id} not found.")
        return AIAnalysis(
            module=graph_id,
            dependencies=[],
            used_by=[],
            analysis=str(err.message),
            simulated=False,
            meta={"graph_found": False},
            errors=[err]
        )

    risk_scores = {}
    hidden_links = []
    cached = data.get("ai_analysis", {})

    if not force_refresh and "ai_analysis" in data:
        logging.info("🚀 Cache Hit! Using existing AI results.")
        risk_scores = cached.get("risk_scores", {})
        hidden_links = cached.get("hidden_links", [])
        # If we have a previously saved module_analysis, return it directly
        if cached.get("module_analysis"):
            try:
                return AIAnalysis(**cached["module_analysis"])
            except Exception as e:
                logging.warning(f"Could not parse cached module_analysis: {e}")

    else:
        logging.info("🧠 Cache Miss. Initiating AI Analysis (Gemini)...")
        risk_scores, hidden_links = await ai_analyzer.run_mri_scan(g)
        
        # Update Data object with raw AI outputs
        data["ai_analysis"] = {
            "risk_scores": risk_scores,
            "hidden_links": hidden_links
        }
        # Save back to disk via Storage
        storage.update_graph_data(graph_id, data)
        logging.info("💾 AI results saved to storage.")

    # --- Generate Textual Report ---
    top_risks = sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)[:]
    report = ["# 🏥 Architectural MRI Report\n"]
    if top_risks:
        report.append("### 🚨 Critical Risk Hotspots:")
        for name, score in top_risks:
            report.append(f"1. **`{name}`** (Risk Score: {score}/10)")
    else:
        report.append("### ✅ System Health: Excellent. No high-risk modules found.")

    report.append("")
    if hidden_links:
        report.append(f"### 👻 Shadow Dependencies ({len(hidden_links)} found):")
        for link in hidden_links[:]:
            report.append(f"- **{link['source']}** ➡️ **{link['target']}** (via {link.get('type', 'Unknown')})")
    else:
        report.append("### 👁️ Visibility: 100%. No hidden dependencies detected.")

    report.append("\n💡 **Next Step:** Run `generate_quick_map` to see the visualization.")
    report_text = "\n".join(report)

    # Save Report via Storage
    storage.save_report(graph_id, report_text)

    # Determine the most central module to summarise
    try:
        central_node = max(nx.degree_centrality(g).items(), key=lambda x: x[1])[0]
    except Exception:
        central_node = None

    dependencies = list(g.successors(central_node)) if central_node else []
    used_by = list(g.predecessors(central_node)) if central_node else []

    # Mark simulated if the AI key is missing
    simulated_flag = not bool(ai_analyzer.api_key)

    meta = {
        "node_count": g.number_of_nodes(),
        "edge_count": g.number_of_edges(),
        "graph_id": graph_id
    }

    ai_summary = AIAnalysis(
        module=central_node or graph_id,
        dependencies=dependencies,
        used_by=used_by,
        analysis=report_text,
        simulated=simulated_flag,
        meta=meta,
        errors=[]
    )

    # Persist the module-level summary for future quick access
    data.setdefault("ai_analysis", {})["module_analysis"] = ai_summary.dict()
    storage.update_graph_data(graph_id, data)

    return ai_summary

@mcp.resource("graph://list")
def list_available_graphs() -> str:
    """
    Retrieves the registry of all repository scans managed by this server.
    
    Use this resource to discover valid `graph_id`s from previous sessions.
    
    Returns:
        str: A newline-separated list formatted as:
        `Folder Path | Graph ID | Last Scan Timestamp`
    """
    index = storage._index
    if not index: return "No scans found."
    lines = []
    for path, meta in index.items():
        lines.append(f"- 📂 `{path}` | 🆔 `{meta['id']}` | 📅 {meta['timestamp']}")
    return "\n".join(lines)

@mcp.resource("graph://{graph_id}/stats")
def get_graph_stats(graph_id: str) -> str:
    """
    Calculates and returns quantitative architectural metrics for a specific graph.
    
    Metrics provided:
    - Node/Edge counts (Size)
    - Graph Density (Coupling indicator)
    - Directed Acyclic Graph (DAG) status (Cycle detection)
    - Weakly Connected Components (Modularity/Isolation)
    
    Returns:
        str: A Markdown-formatted statistical summary.
    """
    g, data = _load_graph(graph_id)
    if not g: return "Graph not found."
    
    density = nx.density(g)
    is_dag = nx.is_directed_acyclic_graph(g)
    components = nx.number_weakly_connected_components(g)
    
    stats = f"""# 📊 Architecture Stats for {graph_id}
- **Total Modules:** {g.number_of_nodes()}
- **Total Connections:** {g.number_of_edges()}
- **Density:** {density:.4f} (Higher = tighter coupling)
- **Cyclic Dependencies:** {'❌ YES (Bad!)' if not is_dag else '✅ NO (Clean)'}
- **Independent Clusters:** {components}
    """
    return stats

@mcp.resource("graph://{graph_id}/risks")
def get_risk_report(graph_id: str) -> str:
    """
    Retrieves the filtered high-risk findings from the AI analysis.
    
    This resource isolates 'Technical Debt' by filtering for modules with 
    a Risk Score > 5. It requires `run_architectural_mri` to have populated 
    the cache first.
    
    Returns:
        str: A Markdown list of high-risk modules and their scores.
    """
    _, data = _load_graph(graph_id)
    if not data or "ai_analysis" not in data: return "No AI analysis found. Run `run_architectural_mri` first."
    
    risks = data["ai_analysis"].get("risk_scores", {})
    # Filter only high risks (> 5)
    high_risks = {k: v for k, v in risks.items() if v > 5}
    sorted_risks = sorted(high_risks.items(), key=lambda x: x[1], reverse=True)
    
    if not sorted_risks: return "✅ No high-risk modules detected."
    
    lines = ["# 🔥 Risk Heatmap (Technical Debt)"]
    for module, score in sorted_risks:
        lines.append(f"- 🔴 **{module}** (Score: {score}/10)")
    return "\n".join(lines)

@mcp.resource("graph://{graph_id}/context/{module_name}")
def get_module_context(graph_id: str, module_name: str) -> str:
    """
    Performs a localized graph traversal (Graph RAG) for a specific module.
    
    This resource extracts the immediate 'neighborhood' of a node to provide 
    context for refactoring or impact analysis.
    
    Returns:
        str: A summary containing:
        - The module's AI Risk Score.
        - 'Used By': List of upstream callers (Predecessors).
        - 'Depends On': List of downstream dependencies (Successors).
    """
    g, data = _load_graph(graph_id)
    if not g: return "Graph not found."
    if module_name not in g: return f"Module '{module_name}' not found in graph."
    
    # 1. Get Neighbors
    predecessors = list(g.predecessors(module_name)) # Who depends on me?
    successors = list(g.successors(module_name))     # Who do I depend on?
    
    # 2. Get AI Metadata if available
    risk = "N/A"
    if "ai_analysis" in data:
        risk = data["ai_analysis"].get("risk_scores", {}).get(module_name, "N/A")
    
    return f"""# 🧩 Context for: `{module_name}`
    
### 🌡️ Risk Score: {risk}/10

### ⬅️ Used By (Callers):
{json.dumps(predecessors, indent=2) if predecessors else "- None (Entry Point?)"}

### ➡️ Depends On (Callees):
{json.dumps(successors, indent=2) if successors else "- None (Leaf Node)"}
"""

if __name__ == "__main__":
    mcp.run()