from mcp.server.fastmcp import FastMCP
import sys
import io
import logging
from services.repository_scanner import RepositoryScanner
from services.graph_generator import GraphGenerator
from services.ai_consultant import AIConsultant
from models.schemas import ScanResult, MapResult, AIAnalysis

# --- FIX FOR WINDOWS ENCODING (Must be at the top) ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
# -----------------------------------------------------

logging.basicConfig(
    filename='server.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

# הגדרת השרת
mcp = FastMCP("Code Cartographer")

# יצירת מופעי השירותים
scanner = RepositoryScanner()
graph_generator = GraphGenerator()
ai_consultant = AIConsultant()


@mcp.tool()
def scan_repository(path: str = ".") -> ScanResult:
    """Scans Python files to build a dependency graph and returns a validated ScanResult."""
    logging.info(f"Tool called: scan_repository with path={path}")
    return scanner.scan(path)


@mcp.tool()
def generate_architecture_map() -> MapResult:
    """Generates a PNG graph of the architecture and returns a validated MapResult."""
    logging.info("Tool called: generate_architecture_map")
    return graph_generator.generate(scanner.get_graph())


@mcp.tool()
async def consult_ai_architect(module_name: str) -> AIAnalysis:
    """Uses Gemini API to analyze a module and returns a validated AIAnalysis."""
    logging.info(f"Tool called: consult_ai_architect with module={module_name}")
    return await ai_consultant.analyze(module_name, scanner.get_graph())


if __name__ == "__main__":
    mcp.run()