"""Proof-of-Work Service - Manages evidence artifacts for pipeline stages.

Structure:
    workspaces/{project_slug}/proof/
    ├── runs/{run_id}/{stage}/
    │   └── {timestamp}_{type}_{description}.{ext}
    └── tasks/{task_id}/{stage}/
        └── {timestamp}_{type}_{description}.{ext}

This folder structure:
- Provides evidence that agents completed their work
- Can be reviewed by Director before approving stage transitions
- Serves as a local data lake for future analytics
- Ready for S3/cloud migration when needed
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.run import Run
from app.models.task import Task

# Base directory for all workspaces
WORKSPACES_DIR = os.environ.get("WORKSPACES_DIR", "workspaces")


class ProofService:
    """Manages proof-of-work artifacts for pipeline stages."""

    ALLOWED_EXTENSIONS = {
        "image": [".png", ".jpg", ".jpeg", ".gif", ".webp"],
        "log": [".txt", ".log", ".md"],
        "data": [".json", ".xml", ".csv"],
    }

    def __init__(self, db: Session):
        self.db = db

    def _get_project_slug(self, project_id: int) -> str:
        """Get a URL-safe slug for the project."""
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return f"project_{project_id}"
        # Simple slugify
        slug = project.name.lower().replace(" ", "_").replace("-", "_")
        return f"{slug}_{project_id}"

    def _ensure_dir(self, path: Path) -> Path:
        """Ensure directory exists and return it."""
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_run_proof_dir(self, run_id: int, stage: str = None) -> Path:
        """Get the proof directory for a run.

        Args:
            run_id: Run ID
            stage: Optional stage subdirectory

        Returns:
            Path to proof directory
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise ValueError(f"Run {run_id} not found")

        project_slug = self._get_project_slug(run.project_id)
        base = Path(WORKSPACES_DIR) / project_slug / "proof" / "runs" / str(run_id)

        if stage:
            base = base / stage

        return self._ensure_dir(base)

    def get_task_proof_dir(self, task_id: int, stage: str = None) -> Path:
        """Get the proof directory for a task.

        Args:
            task_id: Task ID
            stage: Optional stage subdirectory

        Returns:
            Path to proof directory
        """
        task = self.db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.project_id:
            project_slug = self._get_project_slug(task.project_id)
        else:
            project_slug = "unassigned"

        base = Path(WORKSPACES_DIR) / project_slug / "proof" / "tasks" / str(task_id)

        if stage:
            base = base / stage

        return self._ensure_dir(base)

    def save_proof(
        self,
        entity_type: str,  # "run" or "task"
        entity_id: int,
        stage: str,
        proof_type: str,  # "screenshot", "log", "report", etc.
        content: bytes,
        extension: str,
        description: str = ""
    ) -> Dict:
        """Save a proof artifact.

        Args:
            entity_type: "run" or "task"
            entity_id: Run or Task ID
            stage: Pipeline stage (dev, qa, sec, docs)
            proof_type: Type of proof (screenshot, log, report)
            content: File content as bytes
            extension: File extension (with dot)
            description: Optional description for filename

        Returns:
            Dict with path and metadata
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        desc_slug = description.lower().replace(" ", "_")[:30] if description else "proof"
        filename = f"{timestamp}_{proof_type}_{desc_slug}{extension}"

        if entity_type == "run":
            proof_dir = self.get_run_proof_dir(entity_id, stage)
        elif entity_type == "task":
            proof_dir = self.get_task_proof_dir(entity_id, stage)
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")

        filepath = proof_dir / filename

        with open(filepath, "wb") as f:
            f.write(content)

        return {
            "path": str(filepath),
            "filename": filename,
            "stage": stage,
            "proof_type": proof_type,
            "timestamp": timestamp,
            "size": len(content)
        }

    def list_proofs(
        self,
        entity_type: str,
        entity_id: int,
        stage: str = None
    ) -> List[Dict]:
        """List all proof artifacts for an entity.

        Args:
            entity_type: "run" or "task"
            entity_id: Run or Task ID
            stage: Optional filter by stage

        Returns:
            List of proof artifact metadata
        """
        try:
            if entity_type == "run":
                base_dir = self.get_run_proof_dir(entity_id)
            elif entity_type == "task":
                base_dir = self.get_task_proof_dir(entity_id)
            else:
                return []
        except ValueError:
            return []

        proofs = []
        for root, dirs, files in os.walk(base_dir):
            root_path = Path(root)
            current_stage = root_path.name if root_path != base_dir else None

            if stage and current_stage != stage:
                continue

            for filename in files:
                filepath = root_path / filename
                # Format: YYYYMMDD_HHMMSS_type_description.ext
                parts = filename.split("_", 3)  # [date, time, type, desc.ext]

                proofs.append({
                    "path": str(filepath),
                    "filename": filename,
                    "stage": current_stage,
                    "timestamp": f"{parts[0]}_{parts[1]}" if len(parts) > 1 else parts[0] if parts else None,
                    "proof_type": parts[2] if len(parts) > 2 else "unknown",
                    "size": filepath.stat().st_size,
                    "modified": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat()
                })

        # Sort by timestamp descending
        proofs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return proofs

    def get_proof_summary(self, entity_type: str, entity_id: int) -> Dict:
        """Get summary of proofs for an entity.

        Returns count by stage and type.
        """
        proofs = self.list_proofs(entity_type, entity_id)

        by_stage = {}
        by_type = {}

        for proof in proofs:
            stage = proof.get("stage") or "unknown"
            ptype = proof.get("proof_type") or "unknown"

            by_stage[stage] = by_stage.get(stage, 0) + 1
            by_type[ptype] = by_type.get(ptype, 0) + 1

        return {
            "total": len(proofs),
            "by_stage": by_stage,
            "by_type": by_type
        }

    def clear_proofs(self, entity_type: str, entity_id: int, stage: str = None) -> int:
        """Clear proof artifacts.

        Args:
            entity_type: "run" or "task"
            entity_id: Run or Task ID
            stage: Optional - only clear specific stage

        Returns:
            Number of files removed
        """
        try:
            if entity_type == "run":
                base_dir = self.get_run_proof_dir(entity_id)
            elif entity_type == "task":
                base_dir = self.get_task_proof_dir(entity_id)
            else:
                return 0
        except ValueError:
            return 0

        if stage:
            target_dir = base_dir / stage
            if target_dir.exists():
                count = sum(1 for _ in target_dir.iterdir())
                shutil.rmtree(target_dir)
                return count
            return 0

        # Clear all
        if base_dir.exists():
            count = sum(1 for _ in base_dir.rglob("*") if _.is_file())
            shutil.rmtree(base_dir)
            return count
        return 0


def save_screenshot(db: Session, entity_type: str, entity_id: int, stage: str,
                   screenshot_data: bytes, description: str = "screenshot") -> Dict:
    """Convenience function to save a screenshot proof.

    Args:
        db: Database session
        entity_type: "run" or "task"
        entity_id: Run or Task ID
        stage: Pipeline stage
        screenshot_data: PNG image bytes
        description: Description for filename

    Returns:
        Proof metadata dict
    """
    service = ProofService(db)
    return service.save_proof(
        entity_type=entity_type,
        entity_id=entity_id,
        stage=stage,
        proof_type="screenshot",
        content=screenshot_data,
        extension=".png",
        description=description
    )


def save_log(db: Session, entity_type: str, entity_id: int, stage: str,
            log_content: str, description: str = "log") -> Dict:
    """Convenience function to save a log proof.

    Args:
        db: Database session
        entity_type: "run" or "task"
        entity_id: Run or Task ID
        stage: Pipeline stage
        log_content: Log text content
        description: Description for filename

    Returns:
        Proof metadata dict
    """
    service = ProofService(db)
    return service.save_proof(
        entity_type=entity_type,
        entity_id=entity_id,
        stage=stage,
        proof_type="log",
        content=log_content.encode("utf-8"),
        extension=".txt",
        description=description
    )
