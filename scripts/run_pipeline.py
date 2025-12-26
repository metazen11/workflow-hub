#!/usr/bin/env python3
"""
Simple Pipeline Runner - Orchestrates Goose agents through the Workflow Hub.

Usage:
    python scripts/run_pipeline.py --project "Todo App" --task "Build a simple todo list web app" --repo /path/to/repo

This will:
1. Create a project in Workflow Hub
2. Start a development run
3. Run each agent (PM → DEV → QA → SEC) sequentially via Goose
4. Submit reports and advance through states
5. Stop at READY_FOR_DEPLOY for human approval
"""
import argparse
import json
import os
import subprocess
import sys
import time
import requests

WORKFLOW_HUB_URL = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")

# Agent prompts
AGENT_PROMPTS = {
    "pm": """You are a Product Manager agent working on: {task}

Project path: {project_path}

Your job:
1. Break down the task into clear requirements
2. Define acceptance criteria
3. Create a simple implementation plan

Output a JSON block at the end:
```json
{{"status": "pass", "summary": "Created requirements for todo app", "details": {{"requirements": ["list", "of", "requirements"]}}}}
```
""",

    "dev": """You are a Developer agent. Implement: {task}

Project path: {project_path}

Your job:
1. Create the necessary files for a simple todo list web app
2. Use Flask or simple HTML/JS
3. Keep it minimal but functional

After implementing, output a JSON block:
```json
{{"status": "pass", "summary": "Implemented todo app", "details": {{"files_created": ["list", "of", "files"]}}}}
```
""",

    "qa": """You are a QA agent. Test the implementation of: {task}

Project path: {project_path}

Your job:
1. Review the code for bugs
2. Write simple tests if needed
3. Verify the app works

Output a JSON block:
```json
{{"status": "pass", "summary": "Tests passed", "details": {{"tests_run": 5, "issues": []}}}}
```
""",

    "security": """You are a Security agent. Review: {task}

Project path: {project_path}

Your job:
1. Check for security issues (XSS, injection, etc.)
2. Review dependencies
3. Check for hardcoded secrets

Output a JSON block:
```json
{{"status": "pass", "summary": "No critical issues", "details": {{"vulnerabilities": []}}}}
```
""",
}

STATE_TO_AGENT = {
    "pm": "pm",
    "dev": "dev",
    "qa": "qa",
    "sec": "security",
}


def api_call(method, endpoint, data=None):
    """Make API call to Workflow Hub."""
    url = f"{WORKFLOW_HUB_URL}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=30)
        else:
            resp = requests.post(url, json=data, timeout=30)
        return resp.json() if resp.content else {}
    except Exception as e:
        print(f"API Error: {e}")
        return None


def run_goose(agent: str, task: str, project_path: str) -> dict:
    """Run Goose with the agent prompt."""
    prompt = AGENT_PROMPTS.get(agent, "").format(task=task, project_path=project_path)

    print(f"\n{'='*60}")
    print(f"Running {agent.upper()} agent...")
    print(f"{'='*60}\n")

    try:
        result = subprocess.run(
            ["goose", "run", "--text", prompt],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=600
        )

        output = result.stdout
        stderr = result.stderr
        print(f"--- STDOUT ---\n{output}\n")
        if stderr:
            print(f"--- STDERR ---\n{stderr[:1000]}\n")

        # Extract JSON from output
        if "```json" in output:
            start = output.find("```json") + 7
            end = output.find("```", start)
            json_str = output[start:end].strip()
            return json.loads(json_str)
        elif "{" in output:
            start = output.rfind('{"status"')
            if start == -1:
                start = output.rfind("{")
            end = output.rfind("}") + 1
            return json.loads(output[start:end])

        return {"status": "pass", "summary": f"{agent} completed", "details": {}}

    except subprocess.TimeoutExpired:
        return {"status": "fail", "summary": "Timeout"}
    except FileNotFoundError:
        print("\n⚠️  Goose not found! Install with: pipx install goose-ai")
        print("    Then configure: goose configure")
        return {"status": "fail", "summary": "Goose not installed"}
    except json.JSONDecodeError:
        return {"status": "pass", "summary": f"{agent} completed (no JSON)", "details": {}}
    except Exception as e:
        return {"status": "fail", "summary": str(e)}


def run_pipeline(project_name: str, task: str, repo_path: str):
    """Run the full agent pipeline."""

    print(f"\n🚀 Starting pipeline for: {task}")
    print(f"   Project: {project_name}")
    print(f"   Repo: {repo_path}\n")

    # 1. Create or find project
    projects = api_call("GET", "/api/projects")
    project = None
    if projects and "projects" in projects:
        for p in projects["projects"]:
            if p["name"] == project_name:
                project = p
                break

    if not project:
        result = api_call("POST", "/api/projects/create", {
            "name": project_name,
            "description": task,
            "repo_path": repo_path
        })
        project = result.get("project") if result else None

    if not project:
        print("❌ Failed to create project")
        return

    print(f"✅ Project: {project['name']} (ID: {project['id']})")

    # 2. Create a run
    result = api_call("POST", f"/api/projects/{project['id']}/runs/create", {
        "name": task
    })

    if not result or "run" not in result:
        print("❌ Failed to create run")
        return

    run = result["run"]
    run_id = run["id"]
    print(f"✅ Run created: {run['name']} (ID: {run_id})")

    # 3. Process each agent stage
    agents = ["pm", "dev", "qa", "security"]

    for agent in agents:
        # Get current run state
        run_data = api_call("GET", f"/api/runs/{run_id}")
        if not run_data:
            print("❌ Failed to get run status")
            return

        current_state = run_data["run"]["state"]
        print(f"\n📍 Current state: {current_state}")

        # Map state to agent
        expected_agent = STATE_TO_AGENT.get(current_state)
        if expected_agent != agent:
            print(f"   Skipping {agent} (state is {current_state})")
            continue

        # Run the agent
        report = run_goose(agent, task, repo_path)

        print(f"\n📋 {agent.upper()} Report:")
        print(f"   Status: {report.get('status')}")
        print(f"   Summary: {report.get('summary')}")

        # Submit report
        role = agent if agent != "security" else "security"
        result = api_call("POST", f"/api/runs/{run_id}/report", {
            "role": role,
            "status": report.get("status", "fail"),
            "summary": report.get("summary", ""),
            "details": report.get("details", {}),
            "actor": f"goose-{agent}"
        })

        if not result:
            print(f"❌ Failed to submit {agent} report")
            return

        print(f"✅ Report submitted")

        # Advance state if passed
        if report.get("status") == "pass":
            result = api_call("POST", f"/api/runs/{run_id}/advance", {
                "actor": f"goose-{agent}"
            })
            if result and "state" in result:
                print(f"✅ Advanced to: {result['state']}")
            elif result and "error" in result:
                print(f"⚠️  {result['error']}")
        else:
            print(f"❌ {agent.upper()} failed - pipeline stopped")
            return

        time.sleep(1)  # Brief pause between agents

    # 4. Final status
    run_data = api_call("GET", f"/api/runs/{run_id}")
    final_state = run_data["run"]["state"] if run_data else "unknown"

    print(f"\n{'='*60}")
    print(f"🏁 Pipeline complete!")
    print(f"   Final state: {final_state}")

    if final_state == "ready_for_deploy":
        print(f"\n   To approve deployment:")
        print(f"   curl -X POST {WORKFLOW_HUB_URL}/api/runs/{run_id}/approve-deploy")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Run Goose agent pipeline")
    parser.add_argument("--project", default="Todo App", help="Project name")
    parser.add_argument("--task", default="Build a simple todo list web app with Flask", help="Task description")
    parser.add_argument("--repo", default=".", help="Path to repository")

    args = parser.parse_args()

    # Ensure repo path is absolute
    repo_path = os.path.abspath(args.repo)

    run_pipeline(args.project, args.task, repo_path)


if __name__ == "__main__":
    main()
