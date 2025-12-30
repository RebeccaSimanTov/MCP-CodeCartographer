import os
import io
import uuid
import base64
import logging
import networkx as nx
import matplotlib.pyplot as plt
from typing import Union, Optional
from ..models.schemas import MapResult

class GraphGenerator:
    """Service for creating an engineering-style flowchart visualization (Top-Down)."""
    
    def __init__(self, default_filename: str = "architecture_map.png"):
        self.default_filename = default_filename
    
    def generate(self, graph: Union[nx.DiGraph, dict], filename: Optional[str] = None, return_image: bool = False, storage_dir: Optional[str] = None) -> MapResult:
        # Convert serialized graph to networkx if needed
        if isinstance(graph, dict):
            g = nx.DiGraph()
            for node in graph.get("nodes", []):
                if isinstance(node, dict):
                    node_id = node.get("id")
                    attrs = {k: v for k, v in node.items() if k != "id"}
                    g.add_node(node_id, **attrs)
                else:
                    g.add_node(node)
            for u, v in graph.get("edges", []):
                g.add_edge(u, v)
        else:
            g = graph

        if g.number_of_nodes() == 0:
            logging.warning("Attempted to generate map with empty graph")
            return MapResult(success=False, message="Graph is empty.")

        filename = filename or self.default_filename

        try:
            # If a storage_dir is provided, write file atomically into <storage_dir>/images
            saved_path = None
            saved_filename = None
            if storage_dir:
                # storage_dir is expected to be the final images directory (no extra nesting)
                images_dir = os.path.abspath(storage_dir)
                os.makedirs(images_dir, exist_ok=True)
                saved_filename = f"{uuid.uuid4().hex}.png"
                final_path = os.path.join(images_dir, saved_filename)
                tmp_path = final_path + ".tmp"
                # Draw directly to temp file and atomically replace
                self._create_engineering_flowchart(g, tmp_path)
                try:
                    os.replace(tmp_path, final_path)
                except Exception:
                    os.rename(tmp_path, final_path)
                saved_path = os.path.abspath(final_path)
                logging.info(f"Flowchart saved to {saved_path}")

            node_count = g.number_of_nodes()
            edge_count = g.number_of_edges()

            # If return_image requested, always render to memory too
            image_b64 = None
            if return_image:
                buf = io.BytesIO()
                self._create_engineering_flowchart(g, buf)
                buf.seek(0)
                raw_bytes = buf.getvalue()
                image_b64 = base64.b64encode(raw_bytes).decode("ascii")
                logging.info(f"Flowchart generated in-memory ({node_count} nodes)")

            # Compose MapResult
            result = MapResult(
                filename=saved_filename if saved_filename else filename,
                path=saved_path if saved_path else (os.path.abspath(filename) if not storage_dir else saved_path),
                success=True,
                node_count=node_count,
                edge_count=edge_count,
                message=("Flowchart generated." if not saved_path else f"Flowchart saved: {saved_path}"),
                image_bytes=image_b64,
                content_type=("image/png" if image_b64 else None),
            )
            
            if saved_filename and hasattr(result, 'image_filename'):
                 result.image_filename = saved_filename
            if saved_path and hasattr(result, 'image_path'):
                 result.image_path = saved_path

            return result

        except Exception as e:
            error_msg = f"Failed to generate map: {e}"
            logging.error(error_msg, exc_info=True)
            return MapResult(success=False, message=error_msg)

    def _format_label(self, label: str) -> str:
        """
        מפרמט את התווית לתצוגה אנכית ברורה.
        שובר שורה *אחרי* כל נקודה או קו תחתי, אך משאיר אותם.
        """
        # מחליף נקודה ב"נקודה + ירידת שורה"
        formatted = label.replace(".", ".\n")
        # מחליף קו תחתי ב"קו תחתי + ירידת שורה"
        formatted = formatted.replace("_", "_\n")
        return formatted
    
    def _create_engineering_flowchart(self, graph: nx.DiGraph, file_or_path):
        # 1. קנבס ענק
        plt.figure(figsize=(28, 22))
        
        # 2. חישוב מיקומים (Strict Grid)
        pos = {}
        try:
            layers = list(nx.topological_generations(graph))
            y_gap = 10.0 
            x_gap = 8.0  
            for i, layer in enumerate(layers):
                for j, node in enumerate(layer):
                    x = (j - (len(layer) - 1) / 2) * x_gap
                    y = -i * y_gap
                    pos[node] = (x, y)
        except Exception:
            logging.warning("Fallback layout used.")
            pos = nx.spring_layout(graph, k=4.0)

        # 3. עיצוב
        degrees = dict(graph.degree())
        node_colors = [degrees.get(n, 0) for n in graph.nodes()]
        
        # שימוש בפונקציית העיצוב החדשה
        formatted_labels = {node: self._format_label(node) for node in graph.nodes()}
        
        NODE_SIZE = 14000 

        # 4. ציור קווים הנדסיים
        ax = plt.gca()
        for u, v in graph.edges():
            connection_style = "arc,angleA=-90,angleB=90,rad=15"
            try:
                if abs(pos[u][1] - pos[v][1]) < y_gap * 1.1:
                    style = "solid"
                    width = 2.0
                    color = "#666666"
                else:
                    style = "dashed" 
                    width = 1.5
                    color = "#999999"
                    connection_style = "arc,angleA=-90,angleB=90,rad=30"
            except:
                style = "solid"
                width = 2.0
                color = "gray"

            nx.draw_networkx_edges(
                graph, pos,
                edgelist=[(u, v)],
                edge_color=color,
                arrows=True,
                arrowsize=25,
                width=width,
                node_size=NODE_SIZE,
                connectionstyle=connection_style,
                style=style,
                min_source_margin=25,
                min_target_margin=25,
                ax=ax
            )

        # 5. ציור צמתים
        nx.draw_networkx_nodes(
            graph, pos,
            node_size=NODE_SIZE,
            node_color=node_colors,
            cmap=plt.cm.Blues,
            node_shape="s",
            alpha=1.0,
            edgecolors="black",
            linewidths=3.0,
            margins=0.15
        )

        # 6. ציור טקסט (פונט בגודל 10 כדי שייכנס טוב)
        nx.draw_networkx_labels(
            graph, pos,
            labels=formatted_labels,
            font_size=10, 
            font_weight="bold",
            font_family="sans-serif"
        )
        
        plt.title("System Architecture (Hierarchical View)", fontsize=30, pad=50)
        ax.margins(0.30)
        plt.axis("off")
        
        try:
            plt.savefig(file_or_path, format='png', bbox_inches='tight', dpi=150)
        finally:
            plt.close()