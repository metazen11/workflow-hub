#!/usr/bin/env python3
"""Backfill existing filesystem proofs to database.

Scans workspaces/*/proof/ directories and creates Proof records
for any files that don't already have database entries.

Usage:
    source .env && python scripts/backfill_proofs.py
    source .env && python scripts/backfill_proofs.py --dry-run
"""
import os
import sys
import argparse
import mimetypes
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db import get_db
from app.models import Project, Task, Run
from app.models.proof import Proof, ProofType


def detect_proof_type(filename: str) -> ProofType:
    """Detect proof type from filename pattern."""
    lower = filename.lower()
    if 'screenshot' in lower or lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        return ProofType.SCREENSHOT
    elif 'log' in lower or lower.endswith('.log'):
        return ProofType.LOG
    elif 'report' in lower or lower.endswith('.md'):
        return ProofType.REPORT
    elif 'test' in lower:
        return ProofType.TEST_RESULT
    elif 'diff' in lower or 'patch' in lower:
        return ProofType.CODE_DIFF
    else:
        return ProofType.OTHER


def get_file_size(filepath: str) -> int:
    """Get file size in bytes."""
    try:
        return os.path.getsize(filepath)
    except OSError:
        return 0


def extract_timestamp(filename: str) -> datetime:
    """Try to extract timestamp from filename like 20251228_122446_..."""
    try:
        parts = filename.split('_')
        if len(parts) >= 2:
            date_part = parts[0]
            time_part = parts[1]
            if len(date_part) == 8 and len(time_part) == 6:
                return datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
    except (ValueError, IndexError):
        pass
    return datetime.utcnow()


def backfill_proofs(dry_run: bool = False):
    """Backfill filesystem proofs to database."""
    workspaces_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workspaces')

    if not os.path.exists(workspaces_dir):
        print(f"Workspaces directory not found: {workspaces_dir}")
        return

    db = next(get_db())

    try:
        # Build lookup maps for projects, tasks, runs
        projects = {p.id: p for p in db.query(Project).all()}
        project_by_slug = {}
        project_by_id = {}
        for p in projects.values():
            # Store by ID for direct lookup
            project_by_id[p.id] = p
            # Create slug from project folder name
            if p.repo_path:
                folder_name = os.path.basename(p.repo_path)
                project_by_slug[folder_name] = p

        tasks = {t.id: t for t in db.query(Task).all()}
        runs = {r.id: r for r in db.query(Run).all()}

        # Track existing proof filepaths to avoid duplicates
        existing_filepaths = set(p.filepath for p in db.query(Proof.filepath).all())

        created = 0
        skipped = 0
        errors = 0

        # Scan workspaces
        for workspace_name in os.listdir(workspaces_dir):
            workspace_path = os.path.join(workspaces_dir, workspace_name)
            proof_dir = os.path.join(workspace_path, 'proof')

            if not os.path.isdir(proof_dir):
                continue

            # Find project by workspace folder
            # Try multiple matching strategies:
            # 1. Exact folder name match (e.g., "pycrud" -> pycrud project)
            # 2. Folder with ID suffix (e.g., "pycrud_730" -> project 730)
            project = project_by_slug.get(workspace_name)

            if not project:
                # Try to extract project ID from folder name (format: name_id)
                parts = workspace_name.rsplit('_', 1)
                if len(parts) == 2:
                    try:
                        project_id = int(parts[1])
                        project = project_by_id.get(project_id)
                    except ValueError:
                        pass

            if not project:
                print(f"  Warning: No project found for workspace {workspace_name}")
                continue

            print(f"\nScanning {workspace_name} (project {project.id})...")

            # Scan tasks proof dir
            tasks_proof_dir = os.path.join(proof_dir, 'tasks')
            if os.path.isdir(tasks_proof_dir):
                for task_id_str in os.listdir(tasks_proof_dir):
                    task_dir = os.path.join(tasks_proof_dir, task_id_str)
                    if not os.path.isdir(task_dir):
                        continue

                    try:
                        task_id = int(task_id_str)
                    except ValueError:
                        continue

                    task = tasks.get(task_id)
                    if not task:
                        print(f"    Warning: Task {task_id} not found in database")
                        continue

                    # Scan stage directories
                    for stage in os.listdir(task_dir):
                        stage_dir = os.path.join(task_dir, stage)
                        if not os.path.isdir(stage_dir):
                            continue

                        # Scan files
                        for filename in os.listdir(stage_dir):
                            filepath = os.path.join(stage_dir, filename)
                            if not os.path.isfile(filepath):
                                continue

                            if filepath in existing_filepaths:
                                skipped += 1
                                continue

                            # Create proof record
                            proof_type = detect_proof_type(filename)
                            mime_type, _ = mimetypes.guess_type(filepath)
                            file_size = get_file_size(filepath)
                            created_at = extract_timestamp(filename)

                            if dry_run:
                                print(f"    Would create: {filepath}")
                            else:
                                try:
                                    proof = Proof(
                                        project_id=project.id,
                                        task_id=task_id,
                                        run_id=None,  # Task-level proof
                                        stage=stage,
                                        filename=filename,
                                        filepath=filepath,
                                        proof_type=proof_type,
                                        file_size=file_size,
                                        mime_type=mime_type,
                                        description=f"Backfilled from filesystem",
                                        created_by="backfill",
                                        created_at=created_at
                                    )
                                    db.add(proof)
                                    print(f"    Created: {filepath}")
                                except Exception as e:
                                    print(f"    Error creating proof: {e}")
                                    errors += 1
                                    continue

                            created += 1

            # Scan runs proof dir
            runs_proof_dir = os.path.join(proof_dir, 'runs')
            if os.path.isdir(runs_proof_dir):
                for run_id_str in os.listdir(runs_proof_dir):
                    run_dir = os.path.join(runs_proof_dir, run_id_str)
                    if not os.path.isdir(run_dir):
                        continue

                    try:
                        run_id = int(run_id_str)
                    except ValueError:
                        continue

                    run = runs.get(run_id)
                    if not run:
                        print(f"    Warning: Run {run_id} not found in database")
                        continue

                    # Runs don't have task_id - need to find a task for this project
                    # Use the first active task for this project, or skip
                    project_tasks = [t for t in tasks.values() if t.project_id == run.project_id]
                    if not project_tasks:
                        print(f"    Warning: No tasks found for run {run_id}'s project")
                        continue

                    # Use the most recently updated task as the default
                    # This is a best-effort mapping for legacy run proofs
                    task_id = project_tasks[0].id

                    # Scan stage directories
                    for stage in os.listdir(run_dir):
                        stage_dir = os.path.join(run_dir, stage)
                        if not os.path.isdir(stage_dir):
                            continue

                        # Scan files
                        for filename in os.listdir(stage_dir):
                            filepath = os.path.join(stage_dir, filename)
                            if not os.path.isfile(filepath):
                                continue

                            if filepath in existing_filepaths:
                                skipped += 1
                                continue

                            # Create proof record
                            proof_type = detect_proof_type(filename)
                            mime_type, _ = mimetypes.guess_type(filepath)
                            file_size = get_file_size(filepath)
                            created_at = extract_timestamp(filename)

                            if dry_run:
                                print(f"    Would create: {filepath}")
                            else:
                                try:
                                    proof = Proof(
                                        project_id=project.id,
                                        task_id=task_id,
                                        run_id=run_id,  # Run context
                                        stage=stage,
                                        filename=filename,
                                        filepath=filepath,
                                        proof_type=proof_type,
                                        file_size=file_size,
                                        mime_type=mime_type,
                                        description=f"Backfilled from filesystem (run {run_id})",
                                        created_by="backfill",
                                        created_at=created_at
                                    )
                                    db.add(proof)
                                    print(f"    Created: {filepath}")
                                except Exception as e:
                                    print(f"    Error creating proof: {e}")
                                    errors += 1
                                    continue

                            created += 1

        if not dry_run:
            db.commit()

        print(f"\n{'DRY RUN - ' if dry_run else ''}Summary:")
        print(f"  Created: {created}")
        print(f"  Skipped (already exists): {skipped}")
        print(f"  Errors: {errors}")

    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backfill filesystem proofs to database')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    args = parser.parse_args()

    backfill_proofs(dry_run=args.dry_run)
