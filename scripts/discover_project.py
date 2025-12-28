#!/usr/bin/env python3
"""Discover project metadata from an existing codebase.

Analyzes a folder to extract:
- Git repository info (remote, branch)
- Languages and frameworks (from file extensions, config files)
- Tech stack (from package.json, requirements.txt, etc.)
- Key files (README, config files, entry points)
- Build/test/run commands (from package.json, Makefile, etc.)

Usage:
    python scripts/discover_project.py /path/to/project
    python scripts/discover_project.py /path/to/project --create  # Also add to DB
"""
import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from typing import Optional, Dict, List, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ProjectDiscovery:
    """Discover project metadata from folder structure."""

    # File extension to language mapping
    EXTENSION_TO_LANGUAGE = {
        '.py': 'Python',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.jsx': 'JavaScript',
        '.tsx': 'TypeScript',
        '.rb': 'Ruby',
        '.go': 'Go',
        '.rs': 'Rust',
        '.java': 'Java',
        '.kt': 'Kotlin',
        '.swift': 'Swift',
        '.php': 'PHP',
        '.cs': 'C#',
        '.cpp': 'C++',
        '.c': 'C',
        '.html': 'HTML',
        '.css': 'CSS',
        '.scss': 'SCSS',
        '.sass': 'Sass',
        '.vue': 'Vue',
        '.svelte': 'Svelte',
    }

    # Config file to framework mapping
    FRAMEWORK_INDICATORS = {
        'package.json': ['React', 'Vue', 'Angular', 'Express', 'Next.js', 'Nuxt', 'Svelte'],
        'requirements.txt': ['Django', 'Flask', 'FastAPI', 'SQLAlchemy'],
        'Pipfile': ['Django', 'Flask', 'FastAPI'],
        'pyproject.toml': ['Django', 'Flask', 'FastAPI', 'Poetry'],
        'Gemfile': ['Rails', 'Sinatra'],
        'Cargo.toml': ['Rust'],
        'go.mod': ['Go'],
        'composer.json': ['Laravel', 'Symfony', 'WordPress'],
        'pom.xml': ['Spring', 'Maven'],
        'build.gradle': ['Spring', 'Gradle'],
        'wp-config.php': ['WordPress'],
        'docker-compose.yml': ['Docker'],
        'Dockerfile': ['Docker'],
        '.github/workflows': ['GitHub Actions'],
        'Makefile': ['Make'],
        'alembic.ini': ['Alembic', 'SQLAlchemy'],
    }

    # Database indicators
    DATABASE_INDICATORS = {
        'docker-compose.yml': {
            'postgres': 'PostgreSQL',
            'mysql': 'MySQL',
            'mariadb': 'MariaDB',
            'mongo': 'MongoDB',
            'redis': 'Redis',
            'elasticsearch': 'Elasticsearch',
        },
        'requirements.txt': {
            'psycopg': 'PostgreSQL',
            'mysql': 'MySQL',
            'pymongo': 'MongoDB',
            'redis': 'Redis',
            'sqlalchemy': 'SQLAlchemy',
        },
    }

    def __init__(self, path: str):
        self.path = Path(path).resolve()
        if not self.path.exists():
            raise ValueError(f"Path does not exist: {path}")
        if not self.path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

    def discover(self) -> Dict[str, Any]:
        """Run full discovery and return project metadata."""
        result = {
            'name': self.path.name,
            'repo_path': str(self.path),
            'description': None,
            # Git info
            'repository_url': None,
            'repository_ssh_url': None,
            'primary_branch': None,
            # Tech stack
            'languages': [],
            'frameworks': [],
            'databases': [],
            'stack_tags': [],
            # Files
            'key_files': [],
            'entry_point': None,
            'config_files': [],
            # Commands
            'build_command': None,
            'test_command': None,
            'run_command': None,
            # Other
            'default_port': None,
            'python_version': None,
            'node_version': None,
            # Extended discovery
            'docker_services': [],      # Services from docker-compose.yml
            'ci_cd_workflows': [],      # GitHub Actions / CI workflows
            'env_variables': [],        # Required env vars from .env.example
            'api_routes': [],           # Discovered API endpoints
        }

        # Run all discovery methods
        self._discover_git(result)
        self._discover_languages(result)
        self._discover_frameworks(result)
        self._discover_databases(result)
        self._discover_key_files(result)
        self._discover_commands(result)
        self._discover_docker_services(result)
        self._discover_cicd_workflows(result)
        self._discover_env_variables(result)
        self._discover_api_routes(result)
        self._discover_description(result)
        self._build_stack_tags(result)

        return result

    def _discover_git(self, result: Dict):
        """Discover git repository information."""
        git_dir = self.path / '.git'
        if not git_dir.exists():
            return

        try:
            # Get current branch
            branch = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.path,
                capture_output=True,
                text=True
            )
            if branch.returncode == 0 and branch.stdout.strip():
                result['primary_branch'] = branch.stdout.strip()

            # Get remote URL (origin)
            remote = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=self.path,
                capture_output=True,
                text=True
            )
            if remote.returncode == 0 and remote.stdout.strip():
                url = remote.stdout.strip()
                if url.startswith('git@'):
                    result['repository_ssh_url'] = url
                    # Convert SSH to HTTPS for repository_url
                    # git@github.com:user/repo.git -> https://github.com/user/repo.git
                    if 'github.com' in url:
                        https_url = url.replace('git@github.com:', 'https://github.com/')
                        result['repository_url'] = https_url
                else:
                    result['repository_url'] = url

        except Exception as e:
            print(f"Git discovery warning: {e}")

    def _discover_languages(self, result: Dict):
        """Discover programming languages from file extensions."""
        language_counts = {}

        for ext, lang in self.EXTENSION_TO_LANGUAGE.items():
            # Count files with this extension (exclude node_modules, venv, etc.)
            count = 0
            for f in self.path.rglob(f'*{ext}'):
                path_str = str(f)
                if any(skip in path_str for skip in [
                    'node_modules', 'venv', '.venv', '__pycache__',
                    '.git', 'dist', 'build', 'vendor'
                ]):
                    continue
                count += 1

            if count > 0:
                language_counts[lang] = language_counts.get(lang, 0) + count

        # Sort by count and take top languages
        sorted_langs = sorted(language_counts.items(), key=lambda x: x[1], reverse=True)
        result['languages'] = [lang for lang, _ in sorted_langs[:6]]  # Top 6

    def _discover_frameworks(self, result: Dict):
        """Discover frameworks from config files and dependencies."""
        frameworks = set()

        # Check package.json for JS frameworks
        pkg_json = self.path / 'package.json'
        if pkg_json.exists():
            try:
                with open(pkg_json) as f:
                    pkg = json.load(f)
                    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}

                    if 'react' in deps:
                        frameworks.add('React')
                    if 'next' in deps:
                        frameworks.add('Next.js')
                    if 'vue' in deps:
                        frameworks.add('Vue')
                    if 'nuxt' in deps:
                        frameworks.add('Nuxt')
                    if '@angular/core' in deps:
                        frameworks.add('Angular')
                    if 'express' in deps:
                        frameworks.add('Express')
                    if 'svelte' in deps:
                        frameworks.add('Svelte')
                    if 'playwright' in deps:
                        frameworks.add('Playwright')
                    if 'electron' in deps:
                        frameworks.add('Electron')
            except Exception:
                pass

        # Check requirements.txt for Python frameworks
        req_txt = self.path / 'requirements.txt'
        if req_txt.exists():
            try:
                with open(req_txt) as f:
                    content = f.read().lower()
                    if 'django' in content:
                        frameworks.add('Django')
                    if 'flask' in content:
                        frameworks.add('Flask')
                    if 'fastapi' in content:
                        frameworks.add('FastAPI')
                    if 'sqlalchemy' in content:
                        frameworks.add('SQLAlchemy')
                    if 'alembic' in content:
                        frameworks.add('Alembic')
                    if 'pytest' in content:
                        frameworks.add('pytest')
                    if 'pyside' in content or 'pyqt' in content:
                        frameworks.add('Qt/PySide')
            except Exception:
                pass

        # Check pyproject.toml
        pyproject = self.path / 'pyproject.toml'
        if pyproject.exists():
            try:
                with open(pyproject) as f:
                    content = f.read().lower()
                    if 'django' in content:
                        frameworks.add('Django')
                    if 'fastapi' in content:
                        frameworks.add('FastAPI')
                    if 'poetry' in content:
                        frameworks.add('Poetry')
            except Exception:
                pass

        # Check for WordPress
        if (self.path / 'wp-config.php').exists() or (self.path / 'wp-config-sample.php').exists():
            frameworks.add('WordPress')

        # Check for Docker
        if (self.path / 'docker-compose.yml').exists() or (self.path / 'Dockerfile').exists():
            frameworks.add('Docker')

        result['frameworks'] = list(frameworks)

    def _discover_databases(self, result: Dict):
        """Discover databases from config files."""
        databases = set()

        # Check docker-compose.yml
        dc_file = self.path / 'docker-compose.yml'
        if dc_file.exists():
            try:
                with open(dc_file) as f:
                    content = f.read().lower()
                    for indicator, db_name in self.DATABASE_INDICATORS['docker-compose.yml'].items():
                        if indicator in content:
                            databases.add(db_name)
            except Exception:
                pass

        # Check requirements.txt
        req_txt = self.path / 'requirements.txt'
        if req_txt.exists():
            try:
                with open(req_txt) as f:
                    content = f.read().lower()
                    if 'psycopg' in content:
                        databases.add('PostgreSQL')
                    if 'mysql' in content:
                        databases.add('MySQL')
                    if 'pymongo' in content:
                        databases.add('MongoDB')
                    if 'redis' in content:
                        databases.add('Redis')
            except Exception:
                pass

        result['databases'] = list(databases)

    def _discover_key_files(self, result: Dict):
        """Discover important project files."""
        key_files = []
        config_files = []

        # README
        for readme in ['README.md', 'README.rst', 'README.txt', 'README']:
            if (self.path / readme).exists():
                key_files.append(readme)
                break

        # CLAUDE.md (agent instructions)
        if (self.path / 'CLAUDE.md').exists():
            key_files.append('CLAUDE.md')

        # Config files
        config_patterns = [
            'package.json', 'requirements.txt', 'Pipfile', 'pyproject.toml',
            'docker-compose.yml', 'Dockerfile', 'Makefile',
            '.env.example', 'alembic.ini', 'setup.py', 'setup.cfg',
            'tsconfig.json', 'webpack.config.js', 'vite.config.js',
            'wp-config.php', 'composer.json',
        ]
        for pattern in config_patterns:
            if (self.path / pattern).exists():
                config_files.append(pattern)

        # Entry points
        entry_points = ['main.py', 'app.py', 'index.js', 'index.ts', 'manage.py', 'index.php']
        for ep in entry_points:
            if (self.path / ep).exists():
                result['entry_point'] = ep
                break

        result['key_files'] = key_files
        result['config_files'] = config_files

    def _discover_commands(self, result: Dict):
        """Discover build/test/run commands."""
        # From package.json
        pkg_json = self.path / 'package.json'
        if pkg_json.exists():
            try:
                with open(pkg_json) as f:
                    pkg = json.load(f)
                    scripts = pkg.get('scripts', {})

                    if 'build' in scripts:
                        result['build_command'] = 'npm run build'
                    if 'test' in scripts:
                        result['test_command'] = 'npm test'
                    if 'start' in scripts:
                        result['run_command'] = 'npm start'
                    if 'dev' in scripts and not result['run_command']:
                        result['run_command'] = 'npm run dev'
            except Exception:
                pass

        # Python projects
        if (self.path / 'requirements.txt').exists() or (self.path / 'pyproject.toml').exists():
            if (self.path / 'pytest.ini').exists() or (self.path / 'tests').is_dir():
                result['test_command'] = result['test_command'] or 'pytest tests/ -v'

            if (self.path / 'manage.py').exists():
                result['run_command'] = result['run_command'] or 'python manage.py runserver'

        # Docker
        if (self.path / 'docker-compose.yml').exists():
            result['build_command'] = result['build_command'] or 'docker compose up -d'

        # Makefile
        makefile = self.path / 'Makefile'
        if makefile.exists():
            try:
                with open(makefile) as f:
                    content = f.read()
                    if 'test:' in content and not result['test_command']:
                        result['test_command'] = 'make test'
                    if 'build:' in content and not result['build_command']:
                        result['build_command'] = 'make build'
            except Exception:
                pass

    def _discover_docker_services(self, result: Dict):
        """Extract services from docker-compose.yml."""
        dc_files = ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']
        for dc_name in dc_files:
            dc_file = self.path / dc_name
            if dc_file.exists():
                try:
                    import yaml
                    with open(dc_file) as f:
                        compose = yaml.safe_load(f)

                    services = []
                    if compose and 'services' in compose:
                        for svc_name, svc_config in compose['services'].items():
                            svc_info = {'name': svc_name}
                            if isinstance(svc_config, dict):
                                if 'image' in svc_config:
                                    svc_info['image'] = svc_config['image']
                                if 'ports' in svc_config:
                                    svc_info['ports'] = svc_config['ports']
                                if 'build' in svc_config:
                                    svc_info['build'] = True
                            services.append(svc_info)

                    result['docker_services'] = services
                    return
                except ImportError:
                    # PyYAML not installed, try simple parsing
                    try:
                        with open(dc_file) as f:
                            content = f.read()
                        import re
                        services = re.findall(r'^\s{2}(\w+):\s*$', content, re.MULTILINE)
                        result['docker_services'] = [{'name': s} for s in services if s != 'services']
                    except Exception:
                        pass
                except Exception:
                    pass

    def _discover_cicd_workflows(self, result: Dict):
        """Discover CI/CD workflows from .github/workflows."""
        workflows = []

        # GitHub Actions
        gh_workflows = self.path / '.github' / 'workflows'
        if gh_workflows.is_dir():
            for wf_file in gh_workflows.glob('*.yml'):
                try:
                    with open(wf_file) as f:
                        content = f.read()
                    import re
                    name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
                    triggers = re.findall(r'^on:\s*\[?([^\]\n]+)', content, re.MULTILINE)

                    workflows.append({
                        'file': wf_file.name,
                        'name': name_match.group(1).strip() if name_match else wf_file.stem,
                        'triggers': triggers[0].strip() if triggers else 'unknown',
                        'platform': 'GitHub Actions'
                    })
                except Exception:
                    workflows.append({'file': wf_file.name, 'platform': 'GitHub Actions'})

        # GitLab CI
        gitlab_ci = self.path / '.gitlab-ci.yml'
        if gitlab_ci.exists():
            workflows.append({'file': '.gitlab-ci.yml', 'platform': 'GitLab CI'})

        # CircleCI
        circle_ci = self.path / '.circleci' / 'config.yml'
        if circle_ci.exists():
            workflows.append({'file': '.circleci/config.yml', 'platform': 'CircleCI'})

        # Jenkins
        jenkinsfile = self.path / 'Jenkinsfile'
        if jenkinsfile.exists():
            workflows.append({'file': 'Jenkinsfile', 'platform': 'Jenkins'})

        result['ci_cd_workflows'] = workflows

    def _discover_env_variables(self, result: Dict):
        """Extract environment variables from .env.example or .env.sample."""
        env_files = ['.env.example', '.env.sample', '.env.template', 'example.env']
        env_vars = []

        for env_name in env_files:
            env_file = self.path / env_name
            if env_file.exists():
                try:
                    with open(env_file) as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                var_name = line.split('=')[0].strip()
                                # Check if it has a comment describing it
                                env_vars.append(var_name)
                    break
                except Exception:
                    pass

        result['env_variables'] = env_vars[:20]  # Limit to 20 most important

    def _discover_api_routes(self, result: Dict):
        """Discover API routes from code patterns."""
        import re
        routes = []

        # Django/Flask patterns
        patterns = [
            # Django urls.py: path('api/...', ...)
            (r"path\(['\"]([^'\"]+)['\"]", 'urls.py'),
            # Flask: @app.route('/api/...')
            (r"@\w+\.route\(['\"]([^'\"]+)['\"]", '*.py'),
            # FastAPI: @app.get('/api/...')
            (r"@\w+\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]", '*.py'),
            # Express: router.get('/api/...')
            (r"router\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]", '*.js'),
        ]

        # Check common route files
        route_files = [
            'urls.py', 'routes.py', 'api.py',
            'app/urls.py', 'app/routes.py', 'app/views/api.py',
            'src/routes.js', 'routes/index.js', 'server.js', 'app.js'
        ]

        for route_file in route_files:
            file_path = self.path / route_file
            if file_path.exists():
                try:
                    with open(file_path) as f:
                        content = f.read()

                    # Django path() pattern
                    django_routes = re.findall(r"path\(['\"]([^'\"]+)['\"]", content)
                    for r in django_routes:
                        if 'api' in r.lower() or r.startswith('/'):
                            routes.append({'path': r, 'file': route_file})

                    # Flask/FastAPI decorator pattern
                    flask_routes = re.findall(r"@\w+\.(route|get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]", content)
                    for method, path in flask_routes:
                        routes.append({'path': path, 'method': method.upper() if method != 'route' else 'ANY', 'file': route_file})

                except Exception:
                    pass

        # Deduplicate and limit
        seen = set()
        unique_routes = []
        for r in routes:
            key = r.get('path', '')
            if key and key not in seen:
                seen.add(key)
                unique_routes.append(r)

        result['api_routes'] = unique_routes[:30]  # Limit to 30 routes

    def _discover_description(self, result: Dict):
        """Build a rich description from README + discovered features."""
        base_desc = self._extract_readme_description()

        # Build enriched description with tech stack
        parts = []

        # Start with base description if found
        if base_desc:
            parts.append(base_desc)

        # Add tech stack summary
        tech_parts = []
        if result.get('languages'):
            tech_parts.append(f"Languages: {', '.join(result['languages'][:4])}")
        if result.get('frameworks'):
            tech_parts.append(f"Frameworks: {', '.join(result['frameworks'][:4])}")
        if result.get('databases'):
            tech_parts.append(f"Databases: {', '.join(result['databases'][:3])}")

        if tech_parts:
            parts.append("Tech stack: " + "; ".join(tech_parts) + ".")

        # Add key capabilities from config files
        capabilities = []
        if (self.path / 'tests').is_dir() or (self.path / 'pytest.ini').exists():
            capabilities.append("automated tests")
        if (self.path / 'docker-compose.yml').exists():
            capabilities.append("Docker containerization")
        if (self.path / '.github/workflows').is_dir():
            capabilities.append("CI/CD workflows")
        if (self.path / 'alembic.ini').exists():
            capabilities.append("database migrations")
        if (self.path / 'Makefile').exists():
            capabilities.append("Makefile build system")

        if capabilities:
            parts.append(f"Includes: {', '.join(capabilities)}.")

        # Add git info
        if result.get('repository_url'):
            # Extract repo name from URL
            repo_url = result['repository_url']
            if 'github.com' in repo_url:
                parts.append(f"GitHub: {repo_url.split('github.com/')[-1].replace('.git', '')}")

        result['description'] = " ".join(parts) if parts else f"Project at {self.path.name}"

    def _extract_readme_description(self) -> str:
        """Extract meaningful description from README or CLAUDE.md."""
        # Skip these boilerplate phrases
        skip_phrases = [
            'this file provides guidance',
            'claude code',
            'claude.ai',
            'this document',
            'this readme',
            'table of contents',
            'getting started',
            'installation',
        ]

        for readme_name in ['README.md', 'CLAUDE.md', 'README.rst']:
            readme = self.path / readme_name
            if readme.exists():
                try:
                    with open(readme) as f:
                        content = f.read()

                    # Look for ## Project Overview or ## What * Does sections
                    import re
                    overview_match = re.search(
                        r'##\s*(Project Overview|What .+ Does|Overview|About|Description)\s*\n+(.*?)(?=\n##|\n---|\Z)',
                        content,
                        re.IGNORECASE | re.DOTALL
                    )
                    if overview_match:
                        desc = overview_match.group(2).strip()
                        # Clean up markdown
                        desc = re.sub(r'\*\*([^*]+)\*\*', r'\1', desc)  # Remove bold
                        desc = re.sub(r'\n+', ' ', desc)  # Join lines
                        desc = desc[:300]
                        if desc and not any(skip in desc.lower() for skip in skip_phrases):
                            return desc

                    # Fallback: first meaningful paragraph after title
                    lines = content.split('\n')
                    in_content = False
                    paragraph = []
                    for line in lines:
                        line = line.strip()
                        if line.startswith('#'):
                            in_content = True
                            continue
                        if in_content and line:
                            # Skip boilerplate
                            if any(skip in line.lower() for skip in skip_phrases):
                                continue
                            # Skip badges/links at top
                            if line.startswith('[![') or line.startswith('[!'):
                                continue
                            paragraph.append(line)
                            if len(' '.join(paragraph)) > 100:
                                break
                        elif in_content and paragraph:
                            break

                    if paragraph:
                        desc = ' '.join(paragraph)[:300]
                        if not any(skip in desc.lower() for skip in skip_phrases):
                            return desc
                except Exception:
                    pass
        return ""

    def _build_stack_tags(self, result: Dict):
        """Build stack_tags from discovered data."""
        tags = set()

        # Add frameworks as tags (lowercase)
        for fw in result['frameworks']:
            tags.add(fw.lower().replace('.', '').replace(' ', '-'))

        # Add databases as tags
        for db in result['databases']:
            tags.add(db.lower())

        # Add primary languages
        for lang in result['languages'][:3]:  # Top 3
            tags.add(lang.lower())

        result['stack_tags'] = list(tags)


def main():
    parser = argparse.ArgumentParser(description='Discover project metadata from folder')
    parser.add_argument('path', help='Path to project folder')
    parser.add_argument('--create', action='store_true', help='Also create project in database')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    try:
        discovery = ProjectDiscovery(args.path)
        result = discovery.discover()

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"PROJECT DISCOVERY: {result['name']}")
            print(f"{'='*60}")
            print(f"\nPath: {result['repo_path']}")

            if result['repository_url']:
                print(f"Git URL: {result['repository_url']}")
            if result['primary_branch']:
                print(f"Branch: {result['primary_branch']}")

            if result['description']:
                print(f"\nDescription:\n  {result['description'][:200]}...")

            if result['languages']:
                print(f"\nLanguages: {', '.join(result['languages'])}")
            if result['frameworks']:
                print(f"Frameworks: {', '.join(result['frameworks'])}")
            if result['databases']:
                print(f"Databases: {', '.join(result['databases'])}")
            if result['stack_tags']:
                print(f"Tags: {', '.join(result['stack_tags'])}")

            if result['key_files']:
                print(f"\nKey Files: {', '.join(result['key_files'])}")
            if result['entry_point']:
                print(f"Entry Point: {result['entry_point']}")

            if result['build_command']:
                print(f"\nBuild: {result['build_command']}")
            if result['test_command']:
                print(f"Test: {result['test_command']}")
            if result['run_command']:
                print(f"Run: {result['run_command']}")

            # Extended discovery
            if result['docker_services']:
                print(f"\nDocker Services:")
                for svc in result['docker_services'][:5]:
                    img = f" ({svc.get('image', 'build')})" if 'image' in svc or svc.get('build') else ""
                    print(f"  - {svc['name']}{img}")

            if result['ci_cd_workflows']:
                print(f"\nCI/CD Workflows:")
                for wf in result['ci_cd_workflows']:
                    print(f"  - {wf.get('name', wf['file'])} [{wf['platform']}]")

            if result['env_variables']:
                print(f"\nEnvironment Variables ({len(result['env_variables'])}):")
                print(f"  {', '.join(result['env_variables'][:10])}")
                if len(result['env_variables']) > 10:
                    print(f"  ... and {len(result['env_variables']) - 10} more")

            if result['api_routes']:
                print(f"\nAPI Routes ({len(result['api_routes'])}):")
                for route in result['api_routes'][:8]:
                    method = f"[{route.get('method', 'GET')}] " if 'method' in route else ""
                    print(f"  - {method}{route['path']}")
                if len(result['api_routes']) > 8:
                    print(f"  ... and {len(result['api_routes']) - 8} more")

            print()

        if args.create:
            from dotenv import load_dotenv
            load_dotenv()
            from app.db import get_db
            from app.models.project import Project
            from app.models.audit import log_event

            db = next(get_db())
            try:
                project = Project(
                    name=result['name'],
                    description=result['description'],
                    repo_path=result['repo_path'],
                    repository_url=result['repository_url'],
                    repository_ssh_url=result['repository_ssh_url'],
                    primary_branch=result['primary_branch'],
                    languages=result['languages'],
                    frameworks=result['frameworks'],
                    databases=result['databases'],
                    stack_tags=result['stack_tags'],
                    key_files=result['key_files'],
                    entry_point=result['entry_point'],
                    config_files=result['config_files'],
                    build_command=result['build_command'],
                    test_command=result['test_command'],
                    run_command=result['run_command'],
                )
                db.add(project)
                db.commit()
                db.refresh(project)
                log_event(db, "discover_script", "create", "project", project.id, {
                    "name": result['name'],
                    "auto_discovered": True
                })
                print(f"Created project ID: {project.id}")
            finally:
                db.close()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
