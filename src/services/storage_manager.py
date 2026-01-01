import os
import json
import shutil
import logging
import uuid
from datetime import datetime

class StorageManager:
    """
    Manages persistence for Graphs, Images, and Reports.
    Maintains an 'index.json' to map project paths to their latest scan ID,
    ensuring we don't accumulate junk files from repeated scans.
    """
    
    def __init__(self):
        # Base directory
        self.base_dir = os.path.join(os.getcwd(), "mcp_storage")
        
        # Sub-directories
        self.dirs = {
            "graphs": os.path.join(self.base_dir, "graphs"),
            "images": os.path.join(self.base_dir, "images"),
            "reports": os.path.join(self.base_dir, "reports")
        }
        
        # Create directories
        for d in self.dirs.values():
            os.makedirs(d, exist_ok=True)
            
        # Index file path
        self.index_path = os.path.join(self.base_dir, "index.json")
        self._index = self._load_index()

    def _load_index(self):
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, indent=2)

    def save_scan(self, project_path: str, graph_data: dict) -> str:
        """
        Saves a new scan. If this path was scanned before, deletes the old files first.
        Returns the new graph_id.
        """
        abs_path = os.path.abspath(project_path)
        
        # 1. Check if we already have a scan for this path -> Cleanup old files
        if abs_path in self._index:
            old_entry = self._index[abs_path]
            old_id = old_entry.get("id")
            if old_id:
                logging.info(f"♻️ Overwriting previous scan for path: {abs_path} (Old ID: {old_id})")
                self._delete_artifacts(old_id)

        # 2. Generate new ID
        new_id = uuid.uuid4().hex
        
        # 3. Save the Graph JSON
        graph_path = os.path.join(self.dirs["graphs"], f"{new_id}.json")
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)

        # 4. Update Index
        self._index[abs_path] = {
            "id": new_id,
            "timestamp": datetime.now().isoformat(),
            "nodes": len(graph_data.get("nodes", [])),
            "path": abs_path
        }
        self._save_index()
        
        return new_id

    def load_graph(self, graph_id: str):
        path = os.path.join(self.dirs["graphs"], f"{graph_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def update_graph_data(self, graph_id: str, new_data: dict):
        """Used to save AI results back into the JSON."""
        path = os.path.join(self.dirs["graphs"], f"{graph_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)

    def save_image(self, graph_id: str, image_bytes: bytes) -> str:
        path = os.path.join(self.dirs["images"], f"{graph_id}.png")
        with open(path, "wb") as f:
            f.write(image_bytes)
        return path

    def save_report(self, graph_id: str, report_text: str) -> str:
        path = os.path.join(self.dirs["reports"], f"{graph_id}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_text)
        return path
        
    def _delete_artifacts(self, graph_id: str):
        """Helper to remove all files associated with a graph ID."""
        try:
            for dtype, dpath in self.dirs.items():
                # Try extensions .json, .png, .md based on type
                ext = ".json" if dtype == "graphs" else (".png" if dtype == "images" else ".md")
                file_path = os.path.join(dpath, f"{graph_id}{ext}")
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception as e:
            logging.warning(f"Failed to cleanup old artifacts for {graph_id}: {e}")

# Singleton instance to be used by other services
storage = StorageManager()