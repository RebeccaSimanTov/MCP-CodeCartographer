import os
import ast
import logging
import networkx as nx
import json
import uuid
from ..models.schemas import ScanResult

# --- Core setting: MCP internal storage folder ---
MCP_STORAGE_DIR = os.path.join(os.getcwd(), "mcp_storage", "graphs")

class ImportVisitor(ast.NodeVisitor):
    """
    AST visitor that collects all imports from a Python file.
    Supports import, from-import, and dynamic imports.
    """
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
        
    def visit_Call(self, node):
        try:
            # support for __import__("name")
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                if node.args and isinstance(node.args[0], ast.Constant):
                    self.imports.append(node.args[0].value)
            # support for importlib.import_module("name")
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                if node.args and isinstance(node.args[0], ast.Constant):
                    self.imports.append(node.args[0].value)
        except Exception:
            pass
        self.generic_visit(node)

class RepositoryScanner:
    """
    Scans a directory, finds Python files, and builds a Dependency Graph.
    """
    
    def __init__(self):
        self._dependency_graph = nx.DiGraph()
        self._valid_files_map = set()
    
    def _get_module_name(self, full_path: str, root_path: str) -> str:
        """Convert file path (src/utils.py) to module name (src.utils)"""
        rel_path = os.path.relpath(full_path, root_path)
        rel_path = rel_path.replace("\\", "/") 
        module_path = os.path.splitext(rel_path)[0]
        module_name = module_path.replace("/", ".")
        return module_name

    def _resolve_import(self, imp_name: str) -> str:
        """
        Try to find which file an import refers to.
        Uses generic suffix-match logic to work across project structures.
        """
        # 1. Exact match
        if imp_name in self._valid_files_map:
            return imp_name

        # 2. Suffix match (robust generic solution)
        dot_imp = f".{imp_name}"
        for valid_file in self._valid_files_map:
            if valid_file.endswith(dot_imp):
                return valid_file

        # 3. Try to peel hierarchy (from a.b.c -> try to find a.b)
        parts = imp_name.split(".")
        for i in range(len(parts), 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in self._valid_files_map:
                return candidate
            
            suffix_candidate = f".{candidate}"
            for valid_file in self._valid_files_map:
                if valid_file.endswith(suffix_candidate):
                    return valid_file
        return None

    def scan(self, path: str = ".") -> ScanResult:
        logging.info(f"Starting scan at path: {path}")
        
        self._dependency_graph.clear()
        self._valid_files_map.clear()
        analyzed_files = 0
        target_path = os.path.abspath(path) if path else os.getcwd()
        errors = []
        found_files = []

        # Extended skip list
        skip_dirs = {
            "venv", ".venv", "env", ".env", "__pycache__", ".git", 
            "node_modules", ".idea", ".vscode", "tests", "test", "docs",
            "mcp_storage", "build", "dist"
        }

        # 1. Collection phase (Collect Files)
        for root, _, files in os.walk(target_path):
            if any(part in skip_dirs for part in root.split(os.sep)):
                continue

            for file in files:
                if file.endswith(".py") and file != "__init__.py":
                    full_path = os.path.join(root, file)
                    module_name = self._get_module_name(full_path, target_path)
                    
                    self._valid_files_map.add(module_name)
                    found_files.append((full_path, module_name))

        # 2. Graph building phase (Build Graph)
        for full_path, module_name in found_files:
            analyzed_files += 1
            # We store the file_path on the node! This is critical for downstream AI
            self._dependency_graph.add_node(module_name, type="module", file_path=full_path)
            
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if not content.strip(): continue
                    tree = ast.parse(content)
                
                visitor = ImportVisitor(full_path)
                visitor.visit(tree)
                
                for imp in visitor.imports:
                    target = self._resolve_import(imp)
                    if target and target != module_name:
                        # --- Important change: add type="explicit" ---
                        # This indicates: "this is a real import from the code; draw it as a normal line"
                        self._dependency_graph.add_edge(module_name, target, type="explicit")
                        
            except Exception as e:
                logging.warning(f"Error parsing {full_path}: {e}")
                pass

        # 3. Save & finish
        most_central = self._find_most_central_node()

        # Convert to JSON (supports NetworkX attributes)
        nodes = [{"id": n, **attrs} for n, attrs in self._dependency_graph.nodes(data=True)]
        edges = [[u, v, attrs] for u, v, attrs in self._dependency_graph.edges(data=True)]
        
        # In the simple version we only store [u, v], but here we could keep attributes for future use.
        # For full compatibility with current server.py, we use a simple edges format,
        # as the server's ScanResult reloads and adds explicit edges if missing.
        # Keeping a simpler file format avoids schema complications.
        simple_edges = [[u, v] for u, v in self._dependency_graph.edges()]
        
        graph_serialized = {"nodes": nodes, "edges": simple_edges}

        graph_id = None
        try:
            os.makedirs(MCP_STORAGE_DIR, exist_ok=True)
            graph_id = uuid.uuid4().hex
            final_path = os.path.join(MCP_STORAGE_DIR, f"{graph_id}.json")
            
            with open(final_path, "w", encoding="utf-8") as gf:
                json.dump(graph_serialized, gf, ensure_ascii=False, indent=2)
            
        except Exception:
            logging.exception("Failed to persist graph")
            graph_id = None
        
        return ScanResult(
            analyzed_files=analyzed_files,
            most_central=most_central,
            path=target_path,
            success=True,
            errors=errors,
            graph=graph_serialized,
            graph_id=graph_id,
        )

    def _find_most_central_node(self) -> str:
        if self._dependency_graph.number_of_nodes() == 0: return "None"
        degrees = dict(self._dependency_graph.degree())
        if not degrees: return "None"
        return max(degrees.items(), key=lambda x: x[1])[0]