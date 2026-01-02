#!/usr/bin/env python3
"""Cleanup test data from the database and filesystem.

Removes all projects with 'test' in the name (case-insensitive) and their related data.
Also cleans up test entries from the ledger (failed claims).
Run after test suite to clean up leftover test data.

Usage:
    source .env && python scripts/cleanup_test_data.py
"""
import os
import sys
import re
import glob
import yaml
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv()

from sqlalchemy import text
from app.db import engine


def cleanup_test_projects():
    """Delete all test projects and related data.

    Matches projects by:
    - Names containing 'test' (case-insensitive)
    - Names ending with 8-character hex suffix (uuid pattern from unique_name())
    - Known test fixture base names
    """
    with engine.connect() as conn:
        # Get test project IDs - comprehensive pattern matching
        result = conn.execute(text("""
            SELECT id FROM projects WHERE
                name ILIKE '%test%'
                OR name ~ '[0-9a-f]{8}$'
                OR name IN ('Other Project', 'Full Stack App', 'Commands Project',
                           'Key Files Project', 'Dev Settings Project', 'Repo Info Project',
                           'Complete Project')
        """))
        project_ids = [row[0] for row in result]

        if not project_ids:
            print("No test projects found.")
            return

        print(f"Found {len(project_ids)} test projects to delete...")

        # Build the IN clause
        ids_str = ','.join(str(id) for id in project_ids)

        # Delete in dependency order - deepest first
        tables_order = [
            # Claims hierarchy (deepest first)
            ("claim_evidence", f"test_id IN (SELECT id FROM claim_tests WHERE claim_id IN (SELECT id FROM claims WHERE project_id IN ({ids_str}) OR task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str}))))"),
            ("claim_tests", f"claim_id IN (SELECT id FROM claims WHERE project_id IN ({ids_str}) OR task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str})))"),
            ("claims", f"project_id IN ({ids_str}) OR task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str}))"),

            # Task-related
            ("task_requirements", f"task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str}))"),
            ("task_attachments", f"task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str}))"),
            ("work_cycles", f"project_id IN ({ids_str})"),

            # Run-related
            ("agent_reports", f"run_id IN (SELECT id FROM runs WHERE project_id IN ({ids_str}))"),
            ("deployment_history", f"run_id IN (SELECT id FROM runs WHERE project_id IN ({ids_str}))"),

            # Direct project dependencies
            ("runs", f"project_id IN ({ids_str})"),
            ("tasks", f"project_id IN ({ids_str})"),
            ("requirements", f"project_id IN ({ids_str})"),
            ("bug_reports", f"project_id IN ({ids_str})"),
            ("credentials", f"project_id IN ({ids_str})"),
            ("environments", f"project_id IN ({ids_str})"),

            # Finally, projects
            ("projects", f"id IN ({ids_str})"),
        ]

        for table, where_clause in tables_order:
            try:
                result = conn.execute(text(f"DELETE FROM {table} WHERE {where_clause}"))
                if result.rowcount > 0:
                    print(f"  Deleted {result.rowcount} rows from {table}")
            except Exception as e:
                # Table might not exist or have different schema
                print(f"  Skipped {table}: {e}")

        conn.commit()

        # Verify
        result = conn.execute(text(
            "SELECT COUNT(*) FROM projects WHERE name ILIKE '%test%'"
        ))
        remaining = result.scalar()

        if remaining == 0:
            print(f"\nSuccessfully deleted all {len(project_ids)} test projects!")
        else:
            print(f"\nWarning: {remaining} test projects remaining (may have additional dependencies)")


def cleanup_test_ledger_entries():
    """Remove test entries from the failed claims ledger.

    Matches entries where project name contains 'test_project' pattern.
    """
    ledger_dir = os.path.join(PROJECT_ROOT, 'ledger')
    index_path = os.path.join(ledger_dir, 'failed_claims.yaml')
    claims_dir = os.path.join(ledger_dir, 'failed_claims')

    if not os.path.exists(index_path):
        return

    # Load index
    with open(index_path, 'r') as f:
        index_data = yaml.safe_load(f) or {'entries': []}

    original_count = len(index_data.get('entries', []))

    # Filter out test entries (project names starting with test_project)
    real_entries = [
        e for e in index_data.get('entries', [])
        if not (e.get('project', '').startswith('test_project') or
                'test' in e.get('project', '').lower())
    ]

    removed_count = original_count - len(real_entries)

    if removed_count > 0:
        # Update index
        index_data['entries'] = real_entries
        with open(index_path, 'w') as f:
            yaml.dump(index_data, f, default_flow_style=False)

        # Remove individual claim files for test entries
        for claim_file in glob.glob(os.path.join(claims_dir, 'FC-*.yaml')):
            with open(claim_file, 'r') as f:
                claim_data = yaml.safe_load(f) or {}
            project = claim_data.get('project', '')
            if project.startswith('test_project') or 'test' in project.lower():
                os.remove(claim_file)

        print(f"  Removed {removed_count} test entries from ledger")


if __name__ == "__main__":
    cleanup_test_projects()
    cleanup_test_ledger_entries()
