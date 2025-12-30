import os
import logging
import networkx as nx
import matplotlib.pyplot as plt
from models.schemas import MapResult

class GraphGenerator:
    """שירות ליצירת ויזואליזציה של גרף הארכיטקטורה בצורת Flowchart."""
    
    def __init__(self, default_filename: str = "architecture_map.png"):
        self.default_filename = default_filename
    
    def generate(self, graph: nx.DiGraph, filename: str = None) -> MapResult:
        """יוצר תרשים PNG של הארכיטקטורה."""
        
        if graph.number_of_nodes() == 0:
            logging.warning("Attempted to generate map with empty graph")
            return MapResult(
                success=False,
                message="Graph is empty. Please run 'scan_repository' first."
            )
        
        filename = filename or self.default_filename
        
        try:
            self._create_flowchart_visualization(graph, filename)
            
            node_count = graph.number_of_nodes()
            edge_count = graph.number_of_edges()
            full_path = os.path.abspath(filename)
            
            logging.info(f"Flowchart generated: {full_path} ({node_count} nodes)")
            
            return MapResult(
                filename=filename,
                path=full_path,
                success=True,
                node_count=node_count,
                edge_count=edge_count,
                message=f"Flowchart generated: {full_path}",
            )
        
        except Exception as e:
            error_msg = f"Failed to generate map: {e}"
            logging.error(error_msg, exc_info=True)
            return MapResult(success=False, message=error_msg)
    
    def _create_flowchart_visualization(self, graph: nx.DiGraph, filename: str):
        """יוצר את הויזואליזציה במראה של תרשים זרימה היררכי."""
        plt.figure(figsize=(12, 10))
        
        # 1. חישוב המיקומים (Layout) - הלב של השינוי!
        try:
            # מנסה לחלק לדורות (Generations) כדי ליצור היררכיה
            # זה יעבוד רק אם אין מעגלים (Circular Imports)
            pos = {}
            layers = list(nx.topological_generations(graph))
            
            for i, layer in enumerate(layers):
                for j, node in enumerate(layer):
                    # חישוב קואורדינטות:
                    # X = המיקום בשורה, Y = מספר השכבה (שלילי כדי שיהיה מלמעלה למטה)
                    pos[node] = (j - len(layer) / 2, -i)
            
            # רווח אנכי קצת יותר גדול למראה נקי
            pos = nx.spring_layout(graph, pos=pos, fixed=pos.keys(), iterations=0)
            
        except Exception:
            # Fallback: אם יש מעגלים בקוד, נחזור לסידור הרגיל והבטוח
            logging.warning("Circular imports detected, falling back to spring layout.")
            pos = nx.spring_layout(graph, k=0.9)

        # 2. עיצוב הוויזואליזציה (סגנון Flowchart)
        
        # צביעה: כחול מקצועי במקום אדום-כחול
        # צמתים עם הרבה חיבורים יהיו כהים יותר
        degrees = dict(graph.degree())
        node_colors = [degrees.get(n, 0) for n in graph.nodes()]

        # ציור הצמתים (Nodes) כריבועים
        nx.draw_networkx_nodes(
            graph, pos,
            node_size=2500,
            node_color=node_colors,
            cmap=plt.cm.Blues,  # סקאלת כחולים
            node_shape="s",     # s = Square (ריבוע)
            alpha=0.9,
            edgecolors="black"  # מסגרת שחורה דקה לכל ריבוע
        )

        # ציור הקווים (Edges) עם קשתות עדינות
        nx.draw_networkx_edges(
            graph, pos,
            edge_color="gray",
            arrows=True,
            arrowsize=20,
            width=1.5,
            connectionstyle="arc3,rad=0.1", # מעקל את הקווים כדי שיראו את הכיוון
            node_size=2500
        )

        # ציור הטקסט (Labels)
        nx.draw_networkx_labels(
            graph, pos,
            font_size=9,
            font_weight="bold",
            font_family="sans-serif"
        )
        
        plt.title("Codebase Architecture Flow", fontsize=16)
        plt.axis("off") # העלמת הצירים והמספרים מסביב
        
        # שמירה באיכות גבוהה עם הסרת שוליים לבנים
        plt.savefig(filename, bbox_inches='tight', dpi=150)
        plt.close()