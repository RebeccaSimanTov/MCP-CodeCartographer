import os
import ast
import logging
import networkx as nx
from models.schemas import ScanResult, ErrorModel


class ImportVisitor(ast.NodeVisitor):
    """AST Visitor לאיסוף imports מקובץ Python."""
    
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
        elif node.level > 0:
            pass
        self.generic_visit(node)


class RepositoryScanner:
    """שירות לסריקת repository - מצב קפדני (ללא תיקיות וללא __init__)."""
    
    def __init__(self):
        self._dependency_graph = nx.DiGraph()
        self._valid_files_map = set()
    
    def get_graph(self) -> nx.DiGraph:
        return self._dependency_graph
    
    def _get_module_name(self, full_path: str, root_path: str) -> str:
        """ממיר נתיב קובץ לשם מודול."""
        rel_path = os.path.relpath(full_path, root_path)
        rel_path = rel_path.replace("\\", "/") # נרמול לווינדוס
        
        # מסיר סיומת
        module_path = os.path.splitext(rel_path)[0]
        module_name = module_path.replace("/", ".")
        
        return module_name

    def scan(self, path: str = ".") -> ScanResult:
        logging.info(f"Starting SUPER-STRICT scan at path: {path}")
        
        self._dependency_graph.clear()
        self._valid_files_map.clear()
        analyzed_files = 0
        target_path = os.path.abspath(path) if path else os.getcwd()
        errors = []
        found_files = []

        # רשימת התעלמות מורחבת
        skip_dirs = {
            "venv", ".venv", "env", ".env", "__pycache__", ".git", 
            "node_modules", ".idea", ".vscode", "tests", "test", "docs"
        }

        # --- שלב 1: איסוף קבצים (דילוג על init) ---
        for root, _, files in os.walk(target_path):
            if any(part in skip_dirs for part in root.split(os.sep)):
                continue

            for file in files:
                # תנאי הברזל: רק קבצי py, ואסור שזה יהיה init או server
                if file.endswith(".py") and file != "__init__.py" and file != "server.py":
                    full_path = os.path.join(root, file)
                    module_name = self._get_module_name(full_path, target_path)
                    
                    self._valid_files_map.add(module_name)
                    found_files.append((full_path, module_name))

        logging.info(f"Filtered list contains {len(found_files)} substantial files.")

        # --- שלב 2: בניית הגרף ---
        for full_path, module_name in found_files:
            analyzed_files += 1
            self._dependency_graph.add_node(module_name, type="module")
            
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if not content.strip(): 
                        continue
                    tree = ast.parse(content)
                
                visitor = ImportVisitor(full_path)
                visitor.visit(tree)
                
                for imp in visitor.imports:
                    target = None
                    
                    # בדיקה 1: האם האימפורט הוא קובץ שקיים ברשימה שלנו?
                    if imp in self._valid_files_map:
                        target = imp
                    
                    # בדיקה 2: חיפוש היררכי (למקרה שמייבאים פונקציה מתוך קובץ)
                    else:
                        parts = imp.split(".")
                        # רצים אחורה כדי למצוא את הקובץ שמכיל את הפונקציה
                        for i in range(len(parts), 0, -1):
                            candidate = ".".join(parts[:i])
                            # הקסם: אנחנו מחברים רק אם המועמד הוא קובץ ברשימה הלבנה שלנו!
                            if candidate in self._valid_files_map and candidate != module_name:
                                target = candidate
                                break
                    
                    if target:
                        self._dependency_graph.add_edge(module_name, target)

            except Exception as e:
                # מתעלמים משגיאות קטנות כדי לא לעצור את הסריקה
                pass

        # --- שלב 3 (חדש): ניקיון יסודי ---
        # הסרת צמתים בודדים (Orphans) - קבצים שלא קשורים לכלום
        # זה ינקה את הגרף מכל הקבצים שסתם "צפים" למעלה
        nodes_to_remove = [
            node for node in self._dependency_graph.nodes()
            if self._dependency_graph.in_degree(node) == 0 and self._dependency_graph.out_degree(node) == 0
        ]
        self._dependency_graph.remove_nodes_from(nodes_to_remove)
        
        logging.info(f"Removed {len(nodes_to_remove)} orphan nodes for clearer graph.")

        most_central = self._find_most_central_node()
        
        return ScanResult(
            analyzed_files=analyzed_files,
            most_central=most_central,
            path=target_path,
            success=True,
            errors=errors,
        )

    def _find_most_central_node(self) -> str:
        if self._dependency_graph.number_of_nodes() == 0:
            return "None"
        degrees = dict(self._dependency_graph.degree())
        if not degrees:
            return "None"
        return max(degrees.items(), key=lambda x: x[1])[0]