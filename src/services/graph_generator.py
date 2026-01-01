import io
import base64
import logging
import networkx as nx
import matplotlib.pyplot as plt
from typing import Optional
from ..models.schemas import MapResult

class GraphGenerator:
    """
    Service for creating an Architectural MRI visualization.
    Refactored to be a 'Pure Service': It generates the image bytes but delegates 
    persistence (saving to disk) to the StorageManager (via the caller).
    """
    
    def __init__(self):
        pass

    def generate_mri_view(self, graph: nx.DiGraph, risk_scores: Optional[dict] = None) -> MapResult:
        """
        Generates the MRI view (Hierarchical Tree + Risk/Hidden overlays).
        Returns a MapResult containing the base64 encoded image string.
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
            # Create a temporary DAG (Directed Acyclic Graph) for layout calculation
            layout_g = nx.DiGraph()
            layout_g.add_nodes_from(graph.nodes())
            
            # Only use explicit edges for the skeleton structure
            explicit_edges = [(u, v) for u, v, d in graph.edges(data=True) if d.get("type") != "hidden"]
            layout_g.add_edges_from(explicit_edges)

            # Cycle breaking logic
            try:
                while not nx.is_directed_acyclic_graph(layout_g):
                    cycle = nx.find_cycle(layout_g)
                    layout_g.remove_edge(cycle[-1][0], cycle[-1][1])
            except Exception:
                pass 

            # Calculate layers
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
            pos = nx.spring_layout(graph, k=4.0, iterations=50)

        # 3. Visual Styling (Nodes)
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

        # 4. Visual Styling (Edges)
        for u, v, data in graph.edges(data=True):
            is_hidden = data.get("type") == "hidden"
            # Ensure connection_style is always defined to avoid UnboundLocalError
            connection_style = "arc3,rad=0.0"
            
            if is_hidden:
                # MRI Style (Hidden)
                color = "#FF0000"
                style = "dashed"
                width = 3.5
                alpha = 0.9
                connection_style = "arc3,rad=-0.4"
            else:
                # Engineering Style (Explicit)
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

        # 5. Draw Nodes & Labels
        nx.draw_networkx_nodes(
            graph, pos,
            node_size=node_sizes,
            node_color=node_colors,
            node_shape="s",
            edgecolors="#222222",
            linewidths=3.0,
            alpha=1.0
        )

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

        # 6. Finalize & Return Bytes (No file saving!)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
        buf.seek(0)
        raw_bytes = buf.getvalue()
        plt.close()

        return MapResult(
            success=True,
            node_count=node_count,
            edge_count=edge_count,
            message="Hierarchical MRI generated.",
            image_bytes=base64.b64encode(raw_bytes).decode("ascii"),
            content_type="image/png"
        )

    def generate(self, graph, risk_scores: Optional[dict] = None) -> MapResult:
        """Alias for compatibility"""
        return self.generate_mri_view(graph, risk_scores)

    def _format_label(self, label: str) -> str:
        formatted = label.replace(".", ".\n")
        formatted = formatted.replace("_", "_\n")
        return formatted