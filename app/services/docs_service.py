"""Documentation generation service.

Scans a project and generates/updates documentation automatically.
"""
import os
import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class DocsService:
    """Service for generating and updating project documentation."""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.docs_dir = self.project_path / "docs"

    def scan_project(self) -> Dict:
        """Scan project and collect documentation info."""
        result = {
            "python_files": [],
            "classes": [],
            "functions": [],
            "routes": [],
            "readme_exists": (self.project_path / "README.md").exists(),
            "docs_dir_exists": self.docs_dir.exists(),
        }

        # Scan Python files
        for py_file in self.project_path.rglob("*.py"):
            if "__pycache__" in str(py_file) or ".venv" in str(py_file):
                continue

            rel_path = py_file.relative_to(self.project_path)
            result["python_files"].append(str(rel_path))

            try:
                with open(py_file, "r") as f:
                    tree = ast.parse(f.read())

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        docstring = ast.get_docstring(node) or ""
                        result["classes"].append({
                            "name": node.name,
                            "file": str(rel_path),
                            "docstring": docstring[:200] if docstring else None,
                            "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                        })
                    elif isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
                        # Top-level functions only
                        if node.col_offset == 0:
                            docstring = ast.get_docstring(node) or ""
                            result["functions"].append({
                                "name": node.name,
                                "file": str(rel_path),
                                "docstring": docstring[:200] if docstring else None,
                                "args": [arg.arg for arg in node.args.args if arg.arg != "self"]
                            })

                    # Look for Flask/Django routes
                    if isinstance(node, ast.FunctionDef):
                        for decorator in node.decorator_list:
                            if isinstance(decorator, ast.Call):
                                if hasattr(decorator.func, 'attr'):
                                    if decorator.func.attr in ('route', 'get', 'post', 'put', 'delete'):
                                        if decorator.args:
                                            route_path = ast.literal_eval(decorator.args[0]) if isinstance(decorator.args[0], ast.Constant) else str(decorator.args[0])
                                            result["routes"].append({
                                                "path": route_path,
                                                "function": node.name,
                                                "file": str(rel_path),
                                                "docstring": ast.get_docstring(node)
                                            })
            except Exception as e:
                pass  # Skip files that can't be parsed

        return result

    def generate_readme(self, project_info: Dict, project_name: str = None) -> str:
        """Generate README.md content from project info."""
        name = project_name or self.project_path.name

        readme = f"""# {name}

## Overview

{self._infer_description(project_info)}

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd {name}

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

```python
# Example usage
from {name.lower().replace('-', '_')} import main

# Initialize and run
main()
```

## Project Structure

```
{name}/
"""
        # Add file structure
        for py_file in sorted(project_info["python_files"])[:10]:
            readme += f"├── {py_file}\n"

        if len(project_info["python_files"]) > 10:
            readme += f"└── ... and {len(project_info['python_files']) - 10} more files\n"

        readme += "```\n\n"

        # Add classes section if any
        if project_info["classes"]:
            readme += "## Classes\n\n"
            for cls in project_info["classes"][:10]:
                readme += f"### `{cls['name']}`\n\n"
                if cls["docstring"]:
                    readme += f"{cls['docstring']}\n\n"
                if cls["methods"]:
                    readme += f"**Methods:** {', '.join(cls['methods'][:5])}\n\n"

        # Add API section if routes found
        if project_info["routes"]:
            readme += "## API Endpoints\n\n"
            readme += "| Method | Path | Description |\n"
            readme += "|--------|------|-------------|\n"
            for route in project_info["routes"][:20]:
                desc = route["docstring"][:50] if route["docstring"] else route["function"]
                readme += f"| GET/POST | `{route['path']}` | {desc} |\n"
            readme += "\n"

        readme += f"""## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License.

---
*Documentation auto-generated on {datetime.now().strftime('%Y-%m-%d')}*
"""
        return readme

    def generate_api_docs(self, project_info: Dict) -> str:
        """Generate API documentation from routes and functions."""
        docs = """# API Reference

This document describes the available API endpoints and functions.

"""
        if project_info["routes"]:
            docs += "## Endpoints\n\n"
            for route in project_info["routes"]:
                docs += f"### `{route['path']}`\n\n"
                docs += f"**Handler:** `{route['function']}`\n\n"
                if route["docstring"]:
                    docs += f"{route['docstring']}\n\n"
                docs += "---\n\n"

        if project_info["functions"]:
            docs += "## Functions\n\n"
            for func in project_info["functions"]:
                docs += f"### `{func['name']}({', '.join(func['args'])})`\n\n"
                docs += f"**File:** `{func['file']}`\n\n"
                if func["docstring"]:
                    docs += f"{func['docstring']}\n\n"
                docs += "---\n\n"

        return docs

    def _infer_description(self, project_info: Dict) -> str:
        """Try to infer project description from code."""
        # Check for common patterns
        if any("flask" in f.lower() for f in project_info["python_files"]):
            return "A Flask-based web application."
        if any("django" in f.lower() for f in project_info["python_files"]):
            return "A Django-based web application."
        if any("crud" in f.lower() for f in project_info["python_files"]):
            return "A CRUD (Create, Read, Update, Delete) application."
        if project_info["routes"]:
            return "A web application with REST API endpoints."
        return "A Python project."

    def update_or_create_docs(self, force: bool = False) -> Dict:
        """Main entry point: scan project and create/update documentation.

        Args:
            force: If True, overwrite existing docs

        Returns:
            Dict with results of documentation generation
        """
        result = {
            "files_created": [],
            "files_updated": [],
            "files_skipped": [],
            "errors": []
        }

        try:
            # Scan project
            project_info = self.scan_project()

            # Create docs directory if needed
            if not self.docs_dir.exists():
                self.docs_dir.mkdir(parents=True)
                result["files_created"].append("docs/")

            # Generate README.md
            readme_path = self.project_path / "README.md"
            if not readme_path.exists() or force:
                readme_content = self.generate_readme(project_info)
                with open(readme_path, "w") as f:
                    f.write(readme_content)
                if readme_path.exists() and not force:
                    result["files_created"].append("README.md")
                else:
                    result["files_updated"].append("README.md")
            else:
                result["files_skipped"].append("README.md (exists)")

            # Generate API docs if routes/functions found
            if project_info["routes"] or project_info["functions"]:
                api_path = self.docs_dir / "API.md"
                if not api_path.exists() or force:
                    api_content = self.generate_api_docs(project_info)
                    with open(api_path, "w") as f:
                        f.write(api_content)
                    if api_path.exists() and not force:
                        result["files_created"].append("docs/API.md")
                    else:
                        result["files_updated"].append("docs/API.md")

            # Add summary stats
            result["stats"] = {
                "python_files": len(project_info["python_files"]),
                "classes": len(project_info["classes"]),
                "functions": len(project_info["functions"]),
                "routes": len(project_info["routes"])
            }

        except Exception as e:
            result["errors"].append(str(e))

        return result


def generate_docs_for_project(project_path: str, force: bool = False) -> Dict:
    """Convenience function to generate docs for a project.

    Args:
        project_path: Path to the project
        force: If True, overwrite existing docs

    Returns:
        Dict with results
    """
    service = DocsService(project_path)
    return service.update_or_create_docs(force=force)
