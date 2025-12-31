import os
import io
import uuid
import base64
import logging
import shutil
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from typing import Union, Optional
from ..models.schemas import MapResult
from .repository_scanner import MCP_STORAGE_DIR

class GraphGenerator:
    """
    Service for creating an Architectural MRI visualization using a Hierarchical (Top-Down) Layout.
    Ensures a TREE structure even if the graph has cycles or hidden links.
    """
    
    def __init__(self, default_filename: str = "architecture_map.png"):
        self.default_filename = default_filename

    def generate_mri_view(self, graph: nx.DiGraph, risk_scores: Optional[dict] = None, filename: Optional[str] = None, storage_dir: Optional[str] = None, return_image: bool = True) -> MapResult:
        """
        Generates the MRI view.
        CRITICAL FIX: Calculates layout based on a 'clean' DAG to force a tree shape,
        then overlays the complex connections (red lines) on top.
        """
        risk_scores = risk_scores or {}

        node_count = graph.number_of_nodes()
        edge_count = graph.number_of_edges()

        # 1. Canvas Setup
        plt.figure(figsize=(28, 24))
        ax = plt.gca()

        # 2. Robust Hierarchical Layout Logic
        pos = {}
        try:
            # Step A: build a 'skeleton' graph for computing positions only
            # Copy the graph and remove anything that prevents forming a tree
            layout_g = nx.DiGraph()
            layout_g.add_nodes_from(graph.nodes())
            
            # Use only regular (explicit) edges; ignore red (hidden) ones for layout
            explicit_edges = [(u, v) for u, v, d in graph.edges(data=True) if d.get("type") != "hidden"]
            layout_g.add_edges_from(explicit_edges)

            # Step B: cycle breaking
            # If there's a cyclic dependency, topological generation fails. We'll break cycles forcibly.
            try:
                while not nx.is_directed_acyclic_graph(layout_g):
                    # Find a cycle and break it (remove its last edge)
                    cycle = nx.find_cycle(layout_g)
                    layout_g.remove_edge(cycle[-1][0], cycle[-1][1])
            except Exception:
                pass # if it fails, continue with fallback

            # Step C: compute layers (the resulting tree)
            layers = list(nx.topological_generations(layout_g))
            
            y_gap = 10.0 
            x_gap = 8.0  
            
            for i, layer in enumerate(layers):
                sorted_layer = sorted(layer)
                for j, node in enumerate(sorted_layer):
                    x = (j - (len(layer) - 1) / 2) * x_gap
                    y = -i * y_gap
                    pos[node] = (x, y)
                    
        except Exception as e:
            logging.warning(f"Layout fallback triggered: {e}")
            # As a last-resort fallback, use spring layout
            pos = nx.spring_layout(graph, k=4.0, iterations=50)

        # 3. Risk Calculation (Size & Color)
        node_sizes = []
        node_colors = []
        base_size = 14000
        
        try: centrality = nx.in_degree_centrality(graph)
        except: centrality = {n:0 for n in graph.nodes()}

        for node in graph.nodes():
            complexity = risk_scores.get(node, 1)
            impact = (centrality.get(node, 0) * 10) + 1
            risk = complexity * impact
            
            node_sizes.append(base_size * (1 + risk/30.0))
            
            if risk > 20:
                node_colors.append(plt.cm.Reds(min(0.8, 0.3 + risk/50.0)))
            else:
                blue_val = 0.2 + min(0.6, centrality.get(node, 0)*3)
                node_colors.append(plt.cm.Blues(blue_val))

        # 4. Draw Edges (Visible Arrows Fix)
        for u, v, data in graph.edges(data=True):
            is_hidden = data.get("type") == "hidden"
            
            connection_style = "arc,angleA=-90,angleB=90,rad=15"
            
            if is_hidden:
                # hidden links (MRI) - red & dashed
                color = "#FF0000"
                style = "dashed"
                width = 3.5
                alpha = 0.9
                connection_style = "arc3,rad=-0.4"
            else:
                # regular connections - gray/black
                try:
                    if abs(pos[u][1] - pos[v][1]) > y_gap * 1.1:
                         style = "dashed"
                         width = 1.5
                         color = "#999999"
                         connection_style = "arc,angleA=-90,angleB=90,rad=30"
                         alpha = 0.7
                    else:
                        style = "solid"
                        width = 2.0
                        color = "#555555"
                        alpha = 0.8
                except:
                    style = "solid"; width=2.0; color="gray"; alpha=0.8

            nx.draw_networkx_edges(
                graph, pos,
                edgelist=[(u,v)],
                edge_color=color,
                style=style,
                width=width,
                alpha=alpha,
                connectionstyle=connection_style,
                arrows=True,
                arrowsize=35,
                arrowstyle='-|>',
                min_source_margin=75,
                min_target_margin=75,
                ax=ax
            )

        # 5. Draw Nodes (Squares)
        nx.draw_networkx_nodes(
            graph, pos,
            node_size=node_sizes,
            node_color=node_colors,
            node_shape="s",
            edgecolors="#222222",
            linewidths=3.0,
            alpha=1.0
        )

        # 6. Labels
        formatted_labels = {node: self._format_label(node) for node in graph.nodes()}
        nx.draw_networkx_labels(
            graph, pos,
            labels=formatted_labels,
            font_size=10, 
            font_weight="bold",
            font_family="sans-serif"
        )

        # Title
        title = "System Architecture (Hierarchical MRI)"
        if risk_scores: title += "\n(Red = High Risk / Hidden Links)"
        plt.title(title, fontsize=32, pad=60)
        plt.axis("off")

        # 7. Render & Save
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
        buf.seek(0)
        raw_bytes = buf.getvalue()
        plt.close()

        # Persist Logic
        mcp_images_dir = os.path.join(os.path.dirname(MCP_STORAGE_DIR), "images")
        os.makedirs(mcp_images_dir, exist_ok=True)
        image_filename = filename if filename else f"{uuid.uuid4().hex}.png"
        mcp_final_path = os.path.join(mcp_images_dir, image_filename)

        try:
            with open(mcp_final_path, "wb") as f:
                f.write(raw_bytes)
        except Exception:
            logging.exception("Failed to persist MRI image")

        caller_path = None
        if storage_dir:
            try:
                os.makedirs(storage_dir, exist_ok=True)
                caller_path = os.path.join(os.path.abspath(storage_dir), image_filename)
                if os.path.abspath(caller_path) != os.path.abspath(mcp_final_path):
                    shutil.copyfile(mcp_final_path, caller_path)
            except Exception:
                logging.exception("Failed to copy image to caller storage")

        result = MapResult(
            filename=image_filename,
            path=os.path.abspath(mcp_final_path),
            success=True,
            node_count=node_count,
            edge_count=edge_count,
            message="Hierarchical MRI generated with visible arrows.",
            image_bytes=base64.b64encode(raw_bytes).decode("ascii") if return_image else None,
            content_type="image/png" if return_image else None,
            image_filename=image_filename,
            image_path=os.path.abspath(mcp_final_path),
        )

        if caller_path:
            result.meta = {"copied_to": caller_path}

        return result

    def generate(self, graph, filename: Optional[str] = None, return_image: bool = False, storage_dir: Optional[str] = None, risk_scores: Optional[dict] = None) -> MapResult:
        return self.generate_mri_view(graph, risk_scores=risk_scores, filename=filename, storage_dir=storage_dir, return_image=return_image)

    def _format_label(self, label: str) -> str:
        formatted = label.replace(".", ".\n")
        formatted = formatted.replace("_", "_\n")
        return formatted