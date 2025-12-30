from mcp.server.fastmcp import FastMCP
import sys
import io
import os
import logging
import json
# ייבוא הנתיב המשותף כדי שהשרת ידע איפה לחפש את הגרפים
from src.services.repository_scanner import RepositoryScanner, MCP_STORAGE_DIR 
from src.services.graph_generator import GraphGenerator
from src.services.ai_consultant import AIConsultant
from src.models.schemas import ScanResult, MapResult, AIAnalysis

# --- FIX FOR WINDOWS ENCODING ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
# --------------------------------

# Ensure an MCP-managed logs directory exists and use a daily rotating file handler (keep 5 days)
from logging.handlers import TimedRotatingFileHandler

logs_dir = os.path.join(os.path.dirname(MCP_STORAGE_DIR), "logs")
os.makedirs(logs_dir, exist_ok=True)
log_file = os.path.join(logs_dir, "server.log")

handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=5, encoding="utf-8")
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(handler)
# Also keep logging to stdout for convenience during development
root_logger.addHandler(logging.StreamHandler(sys.stdout))

mcp = FastMCP("Code Cartographer")

scanner = RepositoryScanner()
graph_generator = GraphGenerator()
ai_consultant = AIConsultant()


@mcp.tool()
def scan_repository(path: str = ".") -> ScanResult:
    """Scans Python files to build a dependency graph."""
    logging.info(f"Tool called: scan_repository with path={path}")
    return scanner.scan(path)


@mcp.tool()
def generate_architecture_map(graph_id: str) -> MapResult:
    """
    Generates a PNG graph of the architecture.
    Expects a `graph_id` returned by `scan_repository`.
    The graph is loaded from the MCP server's internal storage.
    """
    logging.info(f"Tool called: generate_architecture_map with graph_id={graph_id}")
    
    try:
        # טעינה מהתיקייה הפנימית הקבועה (mcp_storage/graphs)
        graph_path = os.path.join(MCP_STORAGE_DIR, f"{graph_id}.json")
        
        if not os.path.exists(graph_path):
             logging.error(f"Graph file not found: {graph_path}")
             return MapResult(success=False, message=f"Graph ID {graph_id} not found locally.")
             
        with open(graph_path, "r", encoding="utf-8") as gf:
            graph_serialized = json.load(gf)
            
    except Exception as e:
        logging.exception("Failed to read graph file")
        return MapResult(success=False, message=str(e))

    # Save generated images under the MCP storage images folder and return the saved path
    images_root = os.path.join(os.path.dirname(MCP_STORAGE_DIR), "images")
    return graph_generator.generate(graph_serialized, return_image=False, storage_dir=images_root)


@mcp.tool()
async def consult_ai_architect(module_name: str) -> AIAnalysis:
    """Uses Gemini API to analyze a module."""
    logging.info(f"Tool called: consult_ai_architect with module={module_name}")
    return await ai_consultant.analyze(module_name, scanner.get_graph())


if __name__ == "__main__":
    # ודא שהתיקייה קיימת בהתחלה
    os.makedirs(MCP_STORAGE_DIR, exist_ok=True)
    mcp.run()