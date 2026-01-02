"""LLM Service - Docker Model Runner integration.

Provides local LLM inference via Docker Model Runner API.
Use for lightweight completions without Goose overhead.
"""
import requests
import json
import os
import base64
import hashlib
from typing import Optional, List, Dict, Any
from pathlib import Path


# =============================================================================
# Image Description Service (Vision LLM)
# =============================================================================

# Cache directory for image descriptions
IMAGE_DESCRIPTION_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    ".cache", "image_descriptions"
)

# Vision model configuration
VISION_MODEL = os.getenv("VISION_MODEL", "ai/qwen3-vl")
VISION_API_URL = os.getenv("VISION_API_URL", "http://localhost:12434/engines/llama.cpp/v1/chat/completions")


def get_image_description(
    image_path: str,
    force_refresh: bool = False,
    include_errors: bool = True,
    include_text: bool = True
) -> Optional[str]:
    """Get a detailed description of an image using vision LLM.

    Checks cache first; if no cached description exists, calls the vision model.

    Args:
        image_path: Absolute path to the image file
        force_refresh: If True, bypass cache and re-analyze
        include_errors: Ask model to identify any error messages
        include_text: Ask model to transcribe all visible text

    Returns:
        Detailed description string, or None if image cannot be processed
    """
    if not image_path or not os.path.exists(image_path):
        return None

    # Generate cache key from image path and modification time
    cache_key = _get_image_cache_key(image_path)

    # Check cache unless force refresh
    if not force_refresh:
        cached = _get_cached_description(cache_key)
        if cached:
            return cached

    # Process image with vision model
    description = _analyze_image_with_vision_model(
        image_path,
        include_errors=include_errors,
        include_text=include_text
    )

    if description:
        _cache_description(cache_key, description, image_path)

    return description


def _get_image_cache_key(image_path: str) -> str:
    """Generate a unique cache key for an image based on path and mtime."""
    try:
        mtime = os.path.getmtime(image_path)
        key_source = f"{image_path}:{mtime}"
        return hashlib.sha256(key_source.encode()).hexdigest()[:16]
    except OSError:
        return hashlib.sha256(image_path.encode()).hexdigest()[:16]


def _get_cached_description(cache_key: str) -> Optional[str]:
    """Retrieve cached image description if available."""
    cache_file = os.path.join(IMAGE_DESCRIPTION_CACHE_DIR, f"{cache_key}.txt")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            pass
    return None


def _cache_description(cache_key: str, description: str, image_path: str) -> None:
    """Cache an image description for future use."""
    try:
        os.makedirs(IMAGE_DESCRIPTION_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(IMAGE_DESCRIPTION_CACHE_DIR, f"{cache_key}.txt")

        # Include metadata header
        header = f"# Image: {image_path}\n# Cached: {__import__('datetime').datetime.now().isoformat()}\n\n"

        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(header + description)
    except Exception as e:
        print(f"Warning: Could not cache image description: {e}")


def _analyze_image_with_vision_model(
    image_path: str,
    include_errors: bool = True,
    include_text: bool = True
) -> Optional[str]:
    """Call vision LLM API to analyze an image.

    Uses Docker Model Runner with Qwen3-VL (or configured vision model).
    """
    try:
        # Read and encode image as base64
        with open(image_path, 'rb') as f:
            image_data = f.read()

        b64_image = base64.b64encode(image_data).decode('utf-8')

        # Determine image MIME type
        ext = Path(image_path).suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp'
        }
        mime_type = mime_types.get(ext, 'image/png')

        # Build the analysis prompt
        prompt_parts = [
            "Analyze this image and provide a detailed, accurate description.",
            "",
            "Please include:",
            "1. **Layout & Structure**: Describe the overall layout, sections, and visual hierarchy",
            "2. **UI Elements**: List all buttons, inputs, dropdowns, tables, cards, and interactive elements",
            "3. **Colors & Styling**: Note the color scheme, fonts, and visual design patterns",
        ]

        if include_text:
            prompt_parts.append("4. **All Visible Text**: Transcribe ALL text exactly as shown (labels, titles, content, values)")

        if include_errors:
            prompt_parts.append("5. **Error Messages**: Identify any error messages, warnings, or status indicators")

        prompt_parts.extend([
            "",
            "Be precise and factual. Do not make assumptions about content you cannot see.",
            "If text is partially visible, note what you can read and indicate uncertainty."
        ])

        prompt = "\n".join(prompt_parts)

        # Call the vision API
        payload = {
            "model": VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}}
                ]
            }],
            "max_tokens": 2000,
            "temperature": 0.1  # Low temperature for factual description
        }

        response = requests.post(
            VISION_API_URL,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=120
        )

        if response.status_code == 200:
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return content.strip()
        else:
            print(f"Vision API error: {response.status_code} - {response.text[:200]}")

    except FileNotFoundError:
        print(f"Image not found: {image_path}")
    except requests.exceptions.Timeout:
        print(f"Vision API timeout for image: {image_path}")
    except requests.exceptions.ConnectionError:
        print(f"Vision API connection error - is Docker Model Runner running?")
    except Exception as e:
        print(f"Error analyzing image: {e}")

    return None


def get_image_descriptions_for_paths(
    paths: List[str],
    force_refresh: bool = False
) -> Dict[str, str]:
    """Get descriptions for multiple image paths.

    Args:
        paths: List of image file paths
        force_refresh: If True, bypass cache

    Returns:
        Dict mapping image path to description (only includes successful analyses)
    """
    results = {}
    for path in paths:
        if path and os.path.exists(path):
            desc = get_image_description(path, force_refresh=force_refresh)
            if desc:
                results[path] = desc
    return results


def extract_image_paths_from_text(text: str) -> List[str]:
    """Extract potential image file paths from text.

    Looks for common patterns like:
    - /absolute/path/to/image.png
    - ./relative/path/image.jpg
    - ~/home/path/screenshot.png
    """
    import re

    # Pattern for file paths ending in image extensions
    pattern = r'(?:^|[\s\(\[\{"\'])([~/\.]?(?:/[\w\-\.]+)+\.(?:png|jpg|jpeg|gif|webp|bmp|PNG|JPG|JPEG|GIF|WEBP|BMP))(?:[\s\)\]\}"\']|$)'

    matches = re.findall(pattern, text)

    # Expand ~ to home directory
    expanded = []
    for match in matches:
        if match.startswith('~'):
            match = os.path.expanduser(match)
        expanded.append(match)

    return expanded


def enrich_text_with_image_descriptions(
    text: str,
    force_refresh: bool = False
) -> str:
    """Find image paths in text and append their descriptions.

    Useful for enriching prompts that reference screenshots.

    Args:
        text: Text that may contain image paths
        force_refresh: If True, re-analyze images

    Returns:
        Original text with image descriptions appended
    """
    image_paths = extract_image_paths_from_text(text)

    if not image_paths:
        return text

    descriptions = get_image_descriptions_for_paths(image_paths, force_refresh)

    if not descriptions:
        return text

    # Append descriptions
    enriched = text + "\n\n---\n## Referenced Image Descriptions\n\n"

    for path, desc in descriptions.items():
        filename = os.path.basename(path)
        enriched += f"### {filename}\n"
        enriched += f"*Path: {path}*\n\n"
        enriched += desc + "\n\n"

    return enriched


def build_agent_prompt(
    project_context: Dict[str, Any],
    task: Dict[str, Any],
    agent_role: str = "dev",
    include_files: List[str] = None,
    role_config: Dict[str, Any] = None
) -> str:
    """Build a structured prompt for an agent with full project context.

    Format follows this structure:
    1. PROJECT DOCUMENTATION - What the project is, how it works
    2. CODING PRINCIPLES - Standards and practices to follow
    3. CURRENT STATE - Todo list, active tasks, recent changes
    4. AVAILABLE COMMANDS - Shell and API commands
    5. TASK ASSIGNMENT - The specific task to perform

    Args:
        project_context: From /api/projects/{id}/context endpoint
        task: Task dict with title, description, acceptance_criteria
        agent_role: Agent role (dev, qa, sec, docs)
        include_files: Specific files to include (default: priority files)
        role_config: RoleConfig dict from database (optional, uses defaults if not provided)

    Returns:
        Formatted prompt string ready for LLM
    """
    project = project_context.get("project", {})
    files = project_context.get("files", {})
    commands = project_context.get("commands", {})

    # Default priority files for context
    priority_files = include_files or [
        "CLAUDE.md",
        "coding_principles.md",
        "todo.json",
        "_spec/BRIEF.md",
        "_spec/WORK_CYCLE.md"
    ]

    sections = []

    # --- SECTION 1: PROJECT DOCUMENTATION ---
    sections.append("=" * 60)
    sections.append("PROJECT DOCUMENTATION")
    sections.append("=" * 60)
    sections.append(f"\n## Project: {project.get('name', 'Unknown')}\n")

    if project.get("description"):
        sections.append(project["description"])
        sections.append("")

    # Add CLAUDE.md if available
    if "CLAUDE.md" in files and files["CLAUDE.md"].get("content"):
        sections.append("### Project Guide (CLAUDE.md)\n")
        sections.append(files["CLAUDE.md"]["content"])
        sections.append("")

    # --- SECTION 2: CODING PRINCIPLES ---
    if "coding_principles.md" in files and files["coding_principles.md"].get("content"):
        sections.append("=" * 60)
        sections.append("CODING PRINCIPLES")
        sections.append("=" * 60)
        sections.append("")
        sections.append(files["coding_principles.md"]["content"])
        sections.append("")

    # --- SECTION 3: CURRENT STATE ---
    sections.append("=" * 60)
    sections.append("CURRENT STATE")
    sections.append("=" * 60)
    sections.append("")

    # Add todo.json if available
    if "todo.json" in files and files["todo.json"].get("content"):
        sections.append("### Current Tasks (todo.json)\n")
        try:
            todos = json.loads(files["todo.json"]["content"])
            if isinstance(todos, list):
                in_progress = [t for t in todos if t.get("status") == "in_progress"]
                pending = [t for t in todos if t.get("status") == "pending"]
                if in_progress:
                    sections.append("**In Progress:**")
                    for t in in_progress[:5]:
                        sections.append(f"- [{t.get('id')}] {t.get('title')}")
                if pending:
                    sections.append("\n**Pending:**")
                    for t in pending[:5]:
                        sections.append(f"- [{t.get('id')}] {t.get('title')}")
            sections.append("")
        except:
            sections.append(files["todo.json"]["content"][:2000])
            sections.append("")

    # Add work_cycle context if available (file-based)
    if "_spec/WORK_CYCLE.md" in files and files["_spec/WORK_CYCLE.md"].get("content"):
        sections.append("### Recent WorkCycle Notes\n")
        work_cycle_content = files["_spec/WORK_CYCLE.md"]["content"]
        # Truncate if too long
        if len(work_cycle_content) > 3000:
            work_cycle_content = work_cycle_content[:3000] + "\n... [truncated]"
        sections.append(work_cycle_content)
        sections.append("")

    # --- SECTION 3.5: TASK HISTORY (DB-backed) ---
    task_history = project_context.get("task_history", [])
    task_proofs = project_context.get("task_proofs", [])

    if task_history or task_proofs:
        sections.append("=" * 60)
        sections.append("TASK HISTORY")
        sections.append("=" * 60)
        sections.append("")
        sections.append("Previous work on this task:\n")

        if task_history:
            sections.append("### Previous WorkCycles")
            for h in task_history[:5]:  # Limit to 5 most recent
                status_icon = "✅" if h.get("report_status") == "pass" else "❌" if h.get("report_status") == "fail" else "⏳"
                sections.append(f"\n**{h.get('stage', 'unknown').upper()}** ({h.get('to_role', 'unknown')}) - {status_icon} {h.get('status', 'unknown')}")
                if h.get("report_summary"):
                    sections.append(f"  Summary: {h['report_summary'][:200]}")
                if h.get("completed_at"):
                    sections.append(f"  Completed: {h['completed_at']}")
            sections.append("")

        if task_proofs:
            sections.append("### Submitted Proofs/Artifacts")
            for p in task_proofs[:5]:  # Limit to 5 most recent
                sections.append(f"- **{p.get('proof_type', 'unknown')}**: {p.get('filename', 'unknown')}")
                if p.get("summary"):
                    sections.append(f"  {p['summary'][:100]}")
            sections.append("")

        sections.append("Use this history to understand what has been tried and what the current state is.\n")

    # --- SECTION 4: AVAILABLE COMMANDS ---
    if commands:
        sections.append("=" * 60)
        sections.append("AVAILABLE COMMANDS")
        sections.append("=" * 60)
        sections.append("")

        # Group commands by type
        shell_cmds = {}
        api_cmds = {}

        for name, value in commands.items():
            if value is None:
                continue
            if isinstance(value, dict):
                desc = value.get("description", "")
                cmd = value.get("command", "")
                entry = f"{desc}\n  `{cmd}`" if desc else f"`{cmd}`"
            else:
                entry = f"`{value}`"

            if name.startswith("api_"):
                api_cmds[name] = entry
            else:
                shell_cmds[name] = entry

        if shell_cmds:
            sections.append("### Shell Commands\n")
            for name, entry in sorted(shell_cmds.items()):
                sections.append(f"**{name}**: {entry}\n")

        if api_cmds:
            sections.append("### API Commands\n")
            for name, entry in sorted(api_cmds.items()):
                sections.append(f"**{name}**: {entry}\n")

    # --- SECTION 5: TASK ASSIGNMENT ---
    sections.append("=" * 60)
    sections.append(f"TASK ASSIGNMENT - Role: {agent_role.upper()}")
    sections.append("=" * 60)
    sections.append("")

    sections.append(f"### Task: {task.get('title', 'No title')}\n")

    if task.get("task_id"):
        sections.append(f"**ID:** {task['task_id']}")
    if task.get("priority"):
        sections.append(f"**Priority:** {task['priority']}")
    if task.get("status"):
        sections.append(f"**Status:** {task['status']}")

    sections.append("")

    if task.get("description"):
        sections.append("**Description:**")
        sections.append(task["description"])
        sections.append("")

    if task.get("acceptance_criteria"):
        sections.append("**Acceptance Criteria:**")
        criteria = task["acceptance_criteria"]
        if isinstance(criteria, list):
            for c in criteria:
                sections.append(f"- {c}")
        else:
            sections.append(str(criteria))
        sections.append("")

    # Role-specific instructions - use provided role_config or fallback defaults
    if role_config and role_config.get("prompt"):
        # Use the role configuration from database with placeholder substitution
        role_prompt = role_config["prompt"]

        # Substitute placeholders with actual project/task values
        substitutions = {
            "{project_path}": project.get("repo_path", ""),
            "{project_name}": project.get("name", ""),
            "{run_id}": str(task.get("run_id", "")),
            "{task_id}": str(task.get("task_id") or task.get("id", "")),
            "{task_title}": task.get("title", ""),
            "{test_command}": project.get("test_command") or commands.get("test", "pytest tests/ -v"),
            "{build_command}": project.get("build_command") or commands.get("build", ""),
            "{run_command}": project.get("run_command") or commands.get("run", ""),
        }
        for placeholder, value in substitutions.items():
            if isinstance(value, str):
                role_prompt = role_prompt.replace(placeholder, value)

        sections.append(f"**Your Role ({role_config.get('name', agent_role.upper())}):**\n")
        sections.append(role_prompt)
    else:
        # Fallback to hardcoded defaults (should be seeded in DB)
        default_instructions = {
            "dev": """**Your Role (DEV):**
- Implement the task according to the coding principles
- Write clean, testable code
- Follow existing patterns in the codebase
- Run tests before marking complete
- Submit proof of work (test output, screenshots)""",

            "qa": """**Your Role (QA):**
- Review the implementation for correctness
- Verify acceptance criteria are met
- Run tests and check coverage
- Report any bugs or issues found
- Mark PASS if criteria met, FAIL with details if not""",

            "sec": """**Your Role (SECURITY):**
- Review code for security vulnerabilities
- Check for OWASP Top 10 issues
- Verify input validation and sanitization
- Check authentication/authorization
- Report findings with severity ratings""",

            "security": """**Your Role (SECURITY):**
- Review code for security vulnerabilities
- Check for OWASP Top 10 issues
- Verify input validation and sanitization
- Check authentication/authorization
- Report findings with severity ratings""",

            "docs": """**Your Role (DOCS):**
- Review and update documentation
- Ensure code is properly documented
- Update README if needed
- Add inline comments for complex logic
- Verify examples are accurate"""
        }
        sections.append(default_instructions.get(agent_role.lower(), default_instructions["dev"]))
    sections.append("")
    sections.append("-" * 60)
    sections.append("BEGIN TASK EXECUTION")
    sections.append("-" * 60)

    return "\n".join(sections)


class LLMService:
    """Client for Docker Model Runner API (OpenAI-compatible)."""

    def __init__(
        self,
        base_url: str = None,
        default_model: str = "ai/qwen3-coder",
        timeout: float = 120.0
    ):
        self.base_url = base_url or os.getenv(
            "DOCKER_MODEL_URL", "http://localhost:12434"
        )
        self.default_model = default_model
        self.timeout = timeout

    def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        response = requests.get(
            f"{self.base_url}/engines/v1/models",
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json().get("data", [])

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> str:
        """Send a chat completion request.

        Args:
            messages: List of {role, content} message dicts
            model: Model to use (default: ai/qwen3-coder)
            temperature: Sampling temperature (0-2)
            max_tokens: Max tokens to generate
            stream: Whether to stream response

        Returns:
            Generated text content
        """
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        response = requests.post(
            f"{self.base_url}/engines/v1/chat/completions",
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def complete(
        self,
        prompt: str,
        system_prompt: str = None,
        **kwargs
    ) -> str:
        """Convenience method for single-turn completion.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            **kwargs: Additional args passed to chat()

        Returns:
            Generated text content
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, **kwargs)

    # --- High-level task methods ---

    def enrich_documentation(
        self,
        code: str,
        language: str = "python",
        include_examples: bool = True
    ) -> str:
        """Generate documentation for code.

        Args:
            code: Source code to document
            language: Programming language
            include_examples: Whether to include usage examples

        Returns:
            Generated documentation/docstring
        """
        example_instruction = "Include example usage." if include_examples else ""

        prompt = f"""Analyze this {language} code and generate comprehensive documentation.
Include: purpose, parameters, return value, exceptions raised.
{example_instruction}

```{language}
{code}
```

Return ONLY the docstring/documentation (with appropriate format for {language})."""

        return self.complete(
            prompt,
            system_prompt="You are a technical documentation expert. Generate clear, concise documentation.",
            temperature=0.3
        )

    def review_code(
        self,
        code: str,
        context: str = "",
        focus_areas: List[str] = None
    ) -> str:
        """Get code review suggestions.

        Args:
            code: Code to review
            context: Additional context about the code
            focus_areas: Specific areas to focus on (bugs, security, performance, style)

        Returns:
            Code review feedback
        """
        areas = focus_areas or ["bugs", "security", "performance", "style"]
        areas_text = ", ".join(areas)

        prompt = f"""Review this code focusing on: {areas_text}

Context: {context or 'General code review'}

```
{code}
```

Provide specific, actionable feedback with line references where applicable."""

        return self.complete(
            prompt,
            system_prompt="You are a senior software engineer performing a thorough code review.",
            temperature=0.4
        )

    def generate_requirements(
        self,
        description: str,
        output_format: str = "json"
    ) -> str:
        """Generate structured requirements from project description.

        Args:
            description: Project/feature description
            output_format: Output format (json, markdown, bullets)

        Returns:
            Structured requirements
        """
        format_instructions = {
            "json": "Output valid JSON with keys: functional_requirements, non_functional_requirements, user_stories, acceptance_criteria",
            "markdown": "Output in markdown with headers for each section",
            "bullets": "Output as bullet points grouped by category"
        }

        prompt = f"""Analyze this project description and generate structured requirements.

Description: {description}

{format_instructions.get(output_format, format_instructions['markdown'])}"""

        return self.complete(
            prompt,
            system_prompt="You are a software requirements analyst. Generate clear, testable requirements.",
            temperature=0.5
        )

    def summarize(
        self,
        text: str,
        max_sentences: int = 3,
        style: str = "concise"
    ) -> str:
        """Summarize text.

        Args:
            text: Text to summarize
            max_sentences: Maximum sentences in summary
            style: Summary style (concise, detailed, bullet)

        Returns:
            Summary text
        """
        style_instructions = {
            "concise": f"Summarize in {max_sentences} sentences or fewer.",
            "detailed": f"Provide a detailed summary in {max_sentences} paragraphs.",
            "bullet": f"Summarize as {max_sentences} bullet points."
        }

        prompt = f"""{style_instructions.get(style, style_instructions['concise'])}

Text to summarize:
{text}"""

        return self.complete(
            prompt,
            system_prompt="You are an expert at extracting key information and summarizing clearly.",
            temperature=0.3
        )

    def extract_json(
        self,
        text: str,
        schema_hint: str = None
    ) -> Dict[str, Any]:
        """Extract structured JSON from text.

        Args:
            text: Text to extract from
            schema_hint: Optional hint about expected structure

        Returns:
            Extracted JSON as dict
        """
        schema_instruction = f"Expected structure: {schema_hint}" if schema_hint else ""

        prompt = f"""Extract structured data from this text and return as valid JSON.
{schema_instruction}

Text:
{text}

Return ONLY valid JSON, no explanation."""

        result = self.complete(
            prompt,
            system_prompt="You extract structured data from text. Always return valid JSON.",
            temperature=0.2
        )

        # Try to parse JSON from response
        try:
            # Handle markdown code blocks
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]
            return json.loads(result.strip())
        except json.JSONDecodeError:
            return {"raw": result, "error": "Could not parse JSON"}


# Singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


class LLMQuery:
    """Dynamic LLM query builder with context from project/run/task.

    Usage:
        # Simple query
        result = LLMQuery(project_id=741).prompt("Summarize this project").execute()

        # Query with task context
        result = LLMQuery(task_id=123).prompt("Generate test cases").execute()

        # Query and save result to field
        result = LLMQuery(project_id=741).prompt("Generate objectives").save_to("objectives").execute()

        # Full context query
        result = LLMQuery(
            project_id=741,
            run_id=45,
            task_id=123
        ).prompt("Review this implementation").execute()

        # Session-based query (maintains conversation history)
        result = LLMQuery(task_id=123).session("task_123").prompt("Write tests").execute()
        # Follow-up in same session (has context from previous)
        result = LLMQuery(task_id=123).session("task_123").prompt("Now add edge cases").execute()
    """

    def __init__(
        self,
        project_id: int = None,
        run_id: int = None,
        task_id: int = None,
        db_session = None
    ):
        self.project_id = project_id
        self.run_id = run_id
        self.task_id = task_id
        self.db_session = db_session

        # Query configuration
        self._prompt: str = None
        self._system_prompt: str = None
        self._destination_target: str = None  # Raw target string
        self._parsed_destination: Dict[str, Any] = None  # Parsed target
        self._include_context: bool = True
        self._context_sections: List[str] = None  # Which sections to include
        self._temperature: float = 0.7
        self._max_tokens: int = None
        self._model: str = None
        self._role: str = None  # Agent role from RoleConfig

        # Session configuration (for conversation persistence)
        self._session_name: str = None
        self._session_obj: "LLMSession" = None  # Loaded session object

        # Built context (populated on execute)
        self._context: Dict[str, Any] = {}

    def prompt(self, prompt: str) -> "LLMQuery":
        """Set the user prompt."""
        self._prompt = prompt
        return self

    def system(self, system_prompt: str) -> "LLMQuery":
        """Set the system prompt."""
        self._system_prompt = system_prompt
        return self

    def save_to(self, target: str) -> "LLMQuery":
        """Save result to a database field using flexible targeting.

        Supports multiple patterns (parsed left-to-right, fails gracefully):

        1. Simple field (uses context IDs):
           "description" → saves to project/run/task from constructor IDs

        2. Entity.field (uses context ID for that entity):
           "project.description" → saves to project from project_id
           "task.notes" → saves to task from task_id

        3. Entity.ID.field (explicit targeting):
           "project.741.description" → saves to project #741
           "task.123.acceptance_criteria" → saves to task #123

        4. Entity[filter].field (where clause):
           "project[name=Workflow Hub].description"
           "task[task_id=WH-001].notes"

        Args:
            target: Target specification string

        Returns:
            self for method chaining

        Examples:
            .save_to("description")  # Uses context
            .save_to("project.objectives")  # Project from context
            .save_to("project.741.tech_stack")  # Explicit ID
            .save_to("task[task_id=WH-001].notes")  # Where clause
        """
        self._destination_target = target
        self._parsed_destination = self._parse_destination(target)
        return self

    def _parse_destination(self, target: str) -> Dict[str, Any]:
        """Parse a destination target string into structured components.

        Security: Uses SQLAlchemy ORM for all queries (parameterized, SQL-injection safe).
        Additional validation:
        - Table names are whitelisted (project, run, task)
        - Field/column names are validated against model metadata
        - Filter values are passed as parameters, never concatenated

        Returns:
            {
                "table": "project"|"run"|"task"|None,
                "id": int|None,
                "field": str,
                "filter": {"column": "value"}|None,
                "source": "explicit"|"context"|"filter"
            }
        """
        import re

        # Default result
        result = {
            "table": None,
            "id": None,
            "field": None,
            "filter": None,
            "source": "context"
        }

        # Sanitize input - only allow safe characters
        # Allow: alphanumeric, underscore, dot, brackets, equals, comma, spaces, quotes
        if not re.match(r'^[\w\.\[\]=,\s\'"]+$', target):
            result["error"] = f"Invalid characters in target: {target}"
            return result

        # Normalize and strip
        target = target.strip()

        # Pattern 4: entity[filter].field - e.g., "project[name=Workflow Hub].description"
        filter_match = re.match(r'^(\w+)\[([^\]]+)\]\.(\w+)$', target)
        if filter_match:
            table, filter_str, field = filter_match.groups()
            result["table"] = table.lower()
            result["field"] = field
            result["source"] = "filter"

            # Parse filter: "key=value" or "key=value,key2=value2"
            result["filter"] = {}
            for part in filter_str.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    # Try to convert to int if it looks like a number
                    v = v.strip().strip("'\"")
                    try:
                        v = int(v)
                    except ValueError:
                        pass
                    result["filter"][k.strip()] = v
            return result

        # Pattern 3: entity.id.field - e.g., "project.741.description"
        explicit_match = re.match(r'^(\w+)\.(\d+)\.(\w+)$', target)
        if explicit_match:
            table, id_str, field = explicit_match.groups()
            result["table"] = table.lower()
            result["id"] = int(id_str)
            result["field"] = field
            result["source"] = "explicit"
            return result

        # Pattern 2: entity.field - e.g., "project.description"
        entity_match = re.match(r'^(\w+)\.(\w+)$', target)
        if entity_match:
            table, field = entity_match.groups()
            # Map table to context ID
            table = table.lower()
            result["table"] = table
            result["field"] = field
            result["source"] = "context"

            # Get ID from constructor context
            if table == "project" and self.project_id:
                result["id"] = self.project_id
            elif table == "task" and self.task_id:
                result["id"] = self.task_id
            elif table == "run" and self.run_id:
                result["id"] = self.run_id
            return result

        # Pattern 1: just field - e.g., "description"
        if re.match(r'^\w+$', target):
            result["field"] = target
            result["source"] = "context"

            # Auto-detect entity from context (prefer most specific)
            if self.task_id:
                result["table"] = "task"
                result["id"] = self.task_id
            elif self.run_id:
                result["table"] = "run"
                result["id"] = self.run_id
            elif self.project_id:
                result["table"] = "project"
                result["id"] = self.project_id
            return result

        # Fallback: treat entire string as field name (will likely fail gracefully)
        result["field"] = target
        return result

    def with_context(self, include: bool = True, sections: List[str] = None) -> "LLMQuery":
        """Configure context inclusion.

        Args:
            include: Whether to include context
            sections: Specific sections to include (project, commands, files, tasks, runs)
        """
        self._include_context = include
        self._context_sections = sections
        return self

    def temperature(self, temp: float) -> "LLMQuery":
        """Set sampling temperature."""
        self._temperature = temp
        return self

    def max_tokens(self, tokens: int) -> "LLMQuery":
        """Set max output tokens."""
        self._max_tokens = tokens
        return self

    def model(self, model_name: str) -> "LLMQuery":
        """Set the model to use."""
        self._model = model_name
        return self

    def role(self, role_name: str) -> "LLMQuery":
        """Set the agent role - fetches RoleConfig from database.

        The role's prompt template will be used as the system prompt,
        with placeholders substituted from project/run/task context.

        Args:
            role_name: Role identifier (dev, qa, security, docs, pm, etc.)
        """
        self._role = role_name
        return self

    def session(self, name: str = None, auto_create: bool = True) -> "LLMQuery":
        """Enable session-based conversation with message persistence.

        Sessions maintain conversation history across multiple LLM calls,
        similar to Goose's session system. Messages are stored in the
        database and included in subsequent requests.

        Args:
            name: Session name (e.g., "task_123"). If not provided,
                  auto-generates from task_id, run_id, or project_id.
            auto_create: Create session if it doesn't exist (default: True)

        Returns:
            self for method chaining

        Example:
            # First call creates session
            LLMQuery(task_id=123).session("task_123").prompt("Write tests").execute()

            # Second call has conversation context from first
            LLMQuery(task_id=123).session("task_123").prompt("Add edge cases").execute()
        """
        if name:
            self._session_name = name
        elif self.task_id:
            self._session_name = f"task_{self.task_id}"
        elif self.run_id:
            self._session_name = f"run_{self.run_id}"
        elif self.project_id:
            self._session_name = f"project_{self.project_id}"
        else:
            # Generate unique session name
            import uuid
            self._session_name = f"session_{uuid.uuid4().hex[:8]}"

        # Load or create session
        self._load_or_create_session(auto_create)
        return self

    def _load_or_create_session(self, auto_create: bool = True):
        """Load existing session or create new one."""
        from app.db import SessionLocal
        from app.models import LLMSession

        session = self.db_session or SessionLocal()
        close_session = self.db_session is None

        try:
            # Try to find existing session by name and project
            query = session.query(LLMSession).filter(
                LLMSession.name == self._session_name,
                LLMSession.active == True
            )

            # Scope to project if available
            if self.project_id:
                query = query.filter(LLMSession.project_id == self.project_id)

            self._session_obj = query.first()

            if not self._session_obj and auto_create:
                # Create new session
                self._session_obj = LLMSession(
                    name=self._session_name,
                    project_id=self.project_id,
                    task_id=self.task_id,
                    run_id=self.run_id,
                    model=self._model,
                    provider="docker",
                    messages=[],
                    created_by=self._role or "system"
                )
                session.add(self._session_obj)
                session.commit()
                session.refresh(self._session_obj)

        finally:
            if close_session and self._session_obj:
                # Detach the object so we can use it later
                session.expunge(self._session_obj)
            if close_session:
                session.close()

    def _persist_session(self, user_prompt: str, assistant_response: str,
                          input_tokens: int = 0, output_tokens: int = 0):
        """Persist messages to session after LLM call."""
        if not self._session_obj:
            return

        from app.db import SessionLocal
        from app.models import LLMSession

        session = self.db_session or SessionLocal()
        close_session = self.db_session is None

        try:
            # Re-fetch the session object in this DB session
            llm_session = session.query(LLMSession).filter(
                LLMSession.id == self._session_obj.id
            ).first()

            if llm_session:
                # Add messages
                llm_session.add_message("user", user_prompt, input_tokens)
                llm_session.add_message("assistant", assistant_response, output_tokens)

                # Update model if specified
                if self._model:
                    llm_session.model = self._model

                session.commit()

        finally:
            if close_session:
                session.close()

    def _get_role_prompt(self) -> str:
        """Get the role's prompt with placeholders substituted."""
        if not hasattr(self, '_role') or not self._role:
            return ""

        from app.db import SessionLocal
        from app.models import RoleConfig

        session = self.db_session or SessionLocal()
        close_session = self.db_session is None

        try:
            role_config = session.query(RoleConfig).filter(
                RoleConfig.role == self._role,
                RoleConfig.active == True
            ).first()

            if not role_config:
                return ""

            prompt = role_config.prompt

            # Substitute placeholders with actual values
            project = self._context.get("project", {})
            task = self._context.get("task", {})
            run = self._context.get("run", {})

            substitutions = {
                "{project_path}": project.get("repo_path", ""),
                "{project_name}": project.get("name", ""),
                "{run_id}": str(run.get("id", "")),
                "{task_id}": str(task.get("id", "")),
                "{task_title}": task.get("title", ""),
                "{test_command}": project.get("test_command", "pytest tests/ -v"),
                "{build_command}": project.get("build_command", ""),
                "{run_command}": project.get("run_command", ""),
            }

            for placeholder, value in substitutions.items():
                prompt = prompt.replace(placeholder, value)

            return prompt

        finally:
            if close_session:
                session.close()

    def _build_context(self) -> str:
        """Build context string from available IDs."""
        if not self._include_context:
            return ""

        sections = []

        # Import models here to avoid circular imports
        from app.db import SessionLocal
        from app.models import Project, Run, Task

        session = self.db_session or SessionLocal()
        close_session = self.db_session is None

        try:
            # Get project context
            project = None
            if self.project_id:
                project = session.query(Project).filter(Project.id == self.project_id).first()
            elif self.task_id:
                task = session.query(Task).filter(Task.id == self.task_id).first()
                if task:
                    project = session.query(Project).filter(Project.id == task.project_id).first()
            elif self.run_id:
                run = session.query(Run).filter(Run.id == self.run_id).first()
                if run:
                    project = session.query(Project).filter(Project.id == run.project_id).first()

            if project:
                self._context["project"] = project.to_dict()
                sections.append(f"## Project: {project.name}")
                if project.description:
                    sections.append(f"\n{project.description}\n")

                # Project location and structure
                if project.repo_path:
                    sections.append(f"**Repository Path:** `{project.repo_path}`")
                if project.languages:
                    sections.append(f"**Languages:** {', '.join(project.languages)}")
                if project.frameworks:
                    sections.append(f"**Frameworks:** {', '.join(project.frameworks)}")

                # Key files for context
                if project.key_files:
                    sections.append(f"**Key Files:** {', '.join(project.key_files[:10])}")
                if project.entry_point:
                    sections.append(f"**Entry Point:** `{project.entry_point}`")

                # Essential commands (build, test, run) - always include
                sections.append("\n### Essential Commands")
                if project.build_command:
                    sections.append(f"- **Build:** `{project.build_command}`")
                if project.test_command:
                    sections.append(f"- **Test:** `{project.test_command}`")
                    # Extract test directory from test command if possible
                    if "tests/" in project.test_command or "test/" in project.test_command:
                        sections.append(f"  - Tests should be placed in the `tests/` directory")
                if project.run_command:
                    sections.append(f"- **Run:** `{project.run_command}`")

                # Additional commands if requested
                if (not self._context_sections or "commands" in self._context_sections):
                    if project.additional_commands:
                        sections.append("\n### Additional Commands")
                        for name, cmd in list(project.additional_commands.items())[:15]:  # Limit to 15
                            if isinstance(cmd, dict):
                                desc = cmd.get("description", "")
                                command = cmd.get("command", "")
                                sections.append(f"- **{name}**: {desc}\n  `{command}`")
                            else:
                                sections.append(f"- **{name}**: `{cmd}`")

            # Get run context if specified
            if self.run_id and (not self._context_sections or "runs" in self._context_sections):
                run = session.query(Run).filter(Run.id == self.run_id).first()
                if run:
                    self._context["run"] = run.to_dict()
                    sections.append(f"\n### Current Run: #{run.id}")
                    sections.append(f"**State:** {run.state}")
                    if run.goal:
                        sections.append(f"**Goal:** {run.goal}")

            # Get task context if specified
            if self.task_id and (not self._context_sections or "tasks" in self._context_sections):
                task = session.query(Task).filter(Task.id == self.task_id).first()
                if task:
                    self._context["task"] = task.to_dict()
                    sections.append(f"\n### Current Task: {task.title}")
                    sections.append(f"**Status:** {task.status}")
                    if task.description:
                        sections.append(f"**Description:** {task.description}")
                    if task.acceptance_criteria:
                        sections.append("**Acceptance Criteria:**")
                        if isinstance(task.acceptance_criteria, list):
                            for c in task.acceptance_criteria:
                                sections.append(f"  - {c}")
                        else:
                            sections.append(f"  {task.acceptance_criteria}")

                    # Add task history (work_cycles and proofs)
                    from app.models import WorkCycle, Proof

                    work_cycles = session.query(WorkCycle).filter(
                        WorkCycle.task_id == self.task_id
                    ).order_by(WorkCycle.created_at.desc()).limit(5).all()

                    if work_cycles:
                        sections.append("\n### Task History")
                        for h in work_cycles:
                            status_icon = "✅" if h.report_status == "pass" else "❌" if h.report_status == "fail" else "⏳"
                            sections.append(f"- **{h.stage.upper() if h.stage else 'unknown'}** ({h.to_role}) {status_icon}")
                            if h.report_summary:
                                sections.append(f"  {h.report_summary[:150]}")
                        self._context["work_cycles"] = [{"stage": h.stage, "to_role": h.to_role, "status": h.report_status, "summary": h.report_summary} for h in work_cycles]

                    proofs = session.query(Proof).filter(
                        Proof.task_id == self.task_id
                    ).order_by(Proof.created_at.desc()).limit(5).all()

                    if proofs:
                        sections.append("\n### Submitted Proofs")
                        for p in proofs:
                            sections.append(f"- **{p.proof_type}**: {p.filename}")
                        self._context["proofs"] = [{"type": p.proof_type, "filename": p.filename} for p in proofs]

        finally:
            if close_session:
                session.close()

        return "\n".join(sections)

    def _save_result(self, result: str) -> Dict[str, Any]:
        """Save the result to the specified destination using parsed target.

        Returns:
            {
                "success": bool,
                "target": "project.741.description",
                "error": "message" | None,
                "hint": "Valid format: table.id.field" | None,
                "available_fields": ["field1", "field2"] | None
            }
        """
        if not self._parsed_destination:
            return {
                "success": False,
                "target": self._destination_target,
                "error": "No destination specified",
                "hint": "Use .save_to('table.id.field') or .save_to('field')"
            }

        dest = self._parsed_destination

        # Check for parse errors
        if dest.get("error"):
            return {
                "success": False,
                "target": self._destination_target,
                "error": dest["error"],
                "hint": "Valid formats: 'field', 'table.field', 'table.123.field', 'table[column=value].field'"
            }

        table = dest.get("table")
        record_id = dest.get("id")
        field = dest.get("field")
        filter_dict = dest.get("filter")

        if not field:
            return {
                "success": False,
                "target": self._destination_target,
                "error": "Could not parse field name from target",
                "hint": "Valid formats: 'field', 'table.field', 'table.123.field', 'table[column=value].field'"
            }

        from app.db import SessionLocal
        from app.models import Project, Run, Task

        # Map table names to models
        table_map = {
            "project": Project,
            "projects": Project,
            "run": Run,
            "runs": Run,
            "task": Task,
            "tasks": Task,
        }

        if table and table not in table_map:
            return {
                "success": False,
                "target": self._destination_target,
                "error": f"Unknown table '{table}'",
                "hint": f"Valid tables: {', '.join(table_map.keys())}"
            }

        session = self.db_session or SessionLocal()
        close_session = self.db_session is None

        try:
            model = table_map.get(table) if table else None
            entity = None

            # Find entity by filter
            if filter_dict and model:
                query = session.query(model)
                for col, val in filter_dict.items():
                    if hasattr(model, col):
                        query = query.filter(getattr(model, col) == val)
                    else:
                        return {
                            "success": False,
                            "target": self._destination_target,
                            "error": f"Column '{col}' not found on {table}",
                            "hint": f"Available columns: {', '.join([c.name for c in model.__table__.columns])}"
                        }
                entity = query.first()
                if not entity:
                    return {
                        "success": False,
                        "target": self._destination_target,
                        "error": f"No {table} found matching filter {filter_dict}",
                        "hint": "Check that the filter values match existing records"
                    }

            # Find entity by explicit ID
            elif record_id and model:
                entity = session.query(model).filter(model.id == record_id).first()
                if not entity:
                    return {
                        "success": False,
                        "target": self._destination_target,
                        "error": f"{table.title()} with id={record_id} not found",
                        "hint": f"Verify the ID exists in the {table} table"
                    }

            # Find entity from context (fallback)
            elif model:
                # Try to get ID from context
                context_id = None
                if table in ("project", "projects"):
                    context_id = self.project_id
                elif table in ("run", "runs"):
                    context_id = self.run_id
                elif table in ("task", "tasks"):
                    context_id = self.task_id

                if context_id:
                    entity = session.query(model).filter(model.id == context_id).first()
                else:
                    return {
                        "success": False,
                        "target": self._destination_target,
                        "error": f"No {table}_id in context to resolve '{self._destination_target}'",
                        "hint": f"Either pass {table}_id to LLMQuery() or use explicit format: {table}.123.{field}"
                    }

            if not entity:
                return {
                    "success": False,
                    "target": self._destination_target,
                    "error": "Could not resolve target entity",
                    "hint": "Use format: table.id.field (e.g., project.741.description)"
                }

            # Check if field exists
            if not hasattr(entity, field):
                available = [c.name for c in entity.__table__.columns]
                return {
                    "success": False,
                    "target": self._destination_target,
                    "error": f"Field '{field}' not found on {table}",
                    "available_fields": available,
                    "hint": f"Available fields: {', '.join(available[:10])}..."
                }

            # Save the result
            setattr(entity, field, result)
            session.commit()

            return {
                "success": True,
                "target": self._destination_target,
                "resolved": f"{table}.{entity.id}.{field}",
                "field": field,
                "table": table,
                "id": entity.id
            }

        except Exception as e:
            session.rollback()
            return {
                "success": False,
                "target": self._destination_target,
                "error": str(e),
                "hint": "Check database connection and field types"
            }
        finally:
            if close_session:
                session.close()

    def execute(self) -> Dict[str, Any]:
        """Execute the LLM query and return result.

        Returns:
            Dict with keys: content, context, saved, model, tokens_estimate, role, session
        """
        if not self._prompt:
            raise ValueError("Prompt is required. Call .prompt() before .execute()")

        # Build context first (needed for role prompt substitution)
        context_str = self._build_context()

        # Determine system prompt - role prompt takes precedence if set
        system_prompt = self._system_prompt
        if self._role:
            role_prompt = self._get_role_prompt()
            if role_prompt:
                # Role prompt becomes system prompt, user's system prompt is prepended if any
                if self._system_prompt:
                    system_prompt = f"{self._system_prompt}\n\n{role_prompt}"
                else:
                    system_prompt = role_prompt

        # Build full prompt (only for non-session calls or first message)
        if context_str:
            full_prompt = f"{context_str}\n\n---\n\n{self._prompt}"
        else:
            full_prompt = self._prompt

        # Execute LLM call
        llm = get_llm_service()

        kwargs = {"temperature": self._temperature}
        if self._max_tokens:
            kwargs["max_tokens"] = self._max_tokens
        if self._model:
            kwargs["model"] = self._model

        # Session-based execution: include conversation history
        session_info = None
        if self._session_obj:
            # Build messages array with history
            messages = []

            # Add system prompt if present
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # Add previous conversation messages (excluding system)
            history = self._session_obj.get_messages_for_api()
            for msg in history:
                if msg["role"] != "system":  # System prompt already added above
                    messages.append(msg)

            # Add current user message
            # For first message, include context; for follow-ups, just the prompt
            if len(history) == 0:
                messages.append({"role": "user", "content": full_prompt})
            else:
                # Follow-up: just add the new prompt
                messages.append({"role": "user", "content": self._prompt})

            # Use chat() with full message history
            content = llm.chat(messages, **kwargs)

            # Persist messages to session
            input_tokens = len(self._prompt.split())
            output_tokens = len(content.split())
            self._persist_session(
                self._prompt if len(history) > 0 else full_prompt,
                content,
                input_tokens,
                output_tokens
            )

            session_info = {
                "id": self._session_obj.id,
                "name": self._session_name,
                "message_count": len(history) + 2,  # +2 for new user/assistant
                "resumed": len(history) > 0
            }
        else:
            # Non-session execution: single completion
            content = llm.complete(
                prompt=full_prompt,
                system_prompt=system_prompt,
                **kwargs
            )

        # Optionally save result to database
        save_result = None
        if self._parsed_destination:
            save_result = self._save_result(content)

        result = {
            "content": content,
            "context": self._context,
            "role": self._role,
            "saved": save_result.get("success", False) if save_result else False,
            "saved_to": save_result if save_result else None,
            "model": self._model or llm.default_model,
            "tokens_estimate": len(full_prompt.split()) + len(content.split())
        }

        if session_info:
            result["session"] = session_info

        return result

    def execute_json(self, schema_hint: str = None) -> Dict[str, Any]:
        """Execute and parse result as JSON.

        Args:
            schema_hint: Optional hint about expected JSON structure
        """
        result = self.execute()
        content = result["content"]

        # Try to parse JSON from response
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            parsed = json.loads(content.strip())
            result["parsed"] = parsed
            result["parse_error"] = None
        except json.JSONDecodeError as e:
            result["parsed"] = None
            result["parse_error"] = str(e)

        return result


def query_llm(
    prompt: str,
    project_id: int = None,
    run_id: int = None,
    task_id: int = None,
    save_to: str = None,
    system_prompt: str = None,
    include_context: bool = True,
    temperature: float = 0.7,
    model: str = None,
    session: str = None,
    db_session = None
) -> Dict[str, Any]:
    """Convenience function for dynamic LLM queries.

    This is the main entry point for flexible LLM queries with automatic
    context building from project/run/task IDs.

    Args:
        prompt: The user prompt
        project_id: Optional project ID for context
        run_id: Optional run ID for context
        task_id: Optional task ID for context
        save_to: Target for saving result. Supports formats:
            - "field" (uses context IDs)
            - "table.field" (uses context ID for table)
            - "table.123.field" (explicit ID)
            - "table[col=val].field" (where clause)
        system_prompt: Optional system prompt
        include_context: Whether to include entity context in prompt
        temperature: Sampling temperature (0-2)
        model: Model to use
        session: Optional session name for conversation persistence
        db_session: Optional existing database session

    Returns:
        Dict with content, context, saved status, model info

    Examples:
        # Simple query with project context
        result = query_llm("Summarize this project", project_id=741)

        # Generate and save to field (uses project_id from context)
        result = query_llm(
            "Generate project objectives as a bullet list",
            project_id=741,
            save_to="objectives"
        )

        # Save to explicit target
        result = query_llm(
            "Generate description",
            save_to="project.741.description"
        )

        # Save with filter
        result = query_llm(
            "Generate tech stack",
            save_to="project[name=Workflow Hub].tech_stack"
        )

        # With session persistence
        result = query_llm(
            "Write initial tests",
            task_id=123,
            session="task_123"
        )
    """
    query = LLMQuery(
        project_id=project_id,
        run_id=run_id,
        task_id=task_id,
        db_session=db_session
    )

    query.prompt(prompt)

    if system_prompt:
        query.system(system_prompt)

    if save_to:
        query.save_to(save_to)

    if session:
        query.session(session)

    query.with_context(include_context)
    query.temperature(temperature)

    if model:
        query.model(model)

    return query.execute()
