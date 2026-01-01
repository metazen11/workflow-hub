#!/usr/bin/env python3
"""MCP Server for Vision Image Analysis.

This server provides Goose with the ability to analyze images using a local
vision LLM (qwen3-vl via Docker Model Runner).

ACCEPTANCE CRITERIA:

AC1: Image Path Detection
  - Detects file paths ending in .png, .jpg, .jpeg, .gif, .webp
  - Supports absolute paths, relative (./), and home (~/) paths
  - Only matches paths to files that actually exist

AC2: Image Analysis
  - Uses vision LLM to generate detailed text description
  - Includes: visible text, errors/warnings, UI elements, layout
  - Caches results based on path + mtime hash

AC3: Prompt Augmentation (Key Feature)
  - Input:  "Check the error at /tmp/error.png"
  - Output: Original prompt + "[Image Analysis: /tmp/error.png]\n{description}"
  - Inline replacement preserves original context

AC4: Multiple Images
  - Detects and analyzes all images in a single prompt
  - Each image gets its own [Image Analysis] block

AC5: Graceful Degradation
  - Missing files: "[Image not found: /path/to/missing.png]"
  - Analysis failures: "[Image analysis failed: /path/to/img.png - {error}]"
  - Never blocks prompt processing

AC6: Caching
  - Cache key: SHA256(path + mtime)[:16]
  - Cache dir: .cache/mcp_vision/
  - Bypass with force_refresh=True

USAGE:

1. As MCP Server (for Goose):
    Add to ~/.config/goose/config.yaml:

    extensions:
      vision:
        type: stdio
        cmd: python3
        args: [/path/to/mcp_vision_server.py, --mcp]

2. As Prompt Preprocessor:
    from mcp_vision_server import preprocess_prompt
    augmented = preprocess_prompt("Check /tmp/error.png")

3. As CLI Tool:
    ./mcp_vision_server.py /path/to/image.png
    ./mcp_vision_server.py --preprocess "Check /tmp/error.png"
"""

import sys
import json
import os
import re
import base64
import hashlib
import requests
from typing import Optional, List, Dict, Any
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =============================================================================
# Configuration
# =============================================================================

VISION_MODEL = os.getenv("VISION_MODEL", "ai/qwen3-vl")
VISION_API_URL = os.getenv("VISION_API_URL", "http://localhost:12434/engines/llama.cpp/v1/chat/completions")
VISION_TIMEOUT = int(os.getenv("VISION_TIMEOUT", "120"))

# Cache directory
CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".cache", "mcp_vision"
)

# Image file extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff'}

# =============================================================================
# Vision Analysis Functions
# =============================================================================

def get_cache_key(image_path: str) -> str:
    """Generate cache key from image path and modification time."""
    try:
        mtime = os.path.getmtime(image_path)
        key_source = f"{image_path}:{mtime}"
        return hashlib.sha256(key_source.encode()).hexdigest()[:16]
    except OSError:
        return hashlib.sha256(image_path.encode()).hexdigest()[:16]


def get_cached_description(cache_key: str) -> Optional[str]:
    """Get cached description if available."""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                return data.get('description')
        except Exception:
            pass
    return None


def cache_description(cache_key: str, description: str, image_path: str) -> None:
    """Cache image description."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        with open(cache_file, 'w') as f:
            json.dump({
                'image_path': image_path,
                'description': description
            }, f)
    except Exception:
        pass


def encode_image_base64(image_path: str) -> Optional[str]:
    """Encode image to base64 for API request."""
    try:
        with open(image_path, 'rb') as f:
            return base64.standard_b64encode(f.read()).decode('utf-8')
    except Exception:
        return None


def get_image_mime_type(image_path: str) -> str:
    """Get MIME type from file extension."""
    ext = Path(image_path).suffix.lower()
    mime_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
        '.tiff': 'image/tiff'
    }
    return mime_types.get(ext, 'image/png')


def analyze_image(
    image_path: str,
    context: str = "",
    include_text: bool = True,
    include_errors: bool = True,
    force_refresh: bool = False,
    compact: bool = False
) -> Dict[str, Any]:
    """Analyze an image using the vision model.

    Args:
        image_path: Path to the image file
        context: Optional context about what to look for
        include_text: Whether to transcribe visible text
        include_errors: Whether to identify error messages
        force_refresh: Bypass cache and re-analyze
        compact: If True, return a brief 2-3 sentence summary instead of full analysis

    Returns:
        Dict with 'success', 'description', and optional 'error'
    """
    # Validate path
    if not os.path.isabs(image_path):
        image_path = os.path.abspath(image_path)

    if not os.path.exists(image_path):
        return {"success": False, "error": f"Image not found: {image_path}"}

    ext = Path(image_path).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        return {"success": False, "error": f"Not an image file: {image_path}"}

    # Check cache (different keys for compact vs full)
    cache_suffix = "_compact" if compact else ""
    cache_key = get_cache_key(image_path) + cache_suffix
    if not force_refresh:
        cached = get_cached_description(cache_key)
        if cached:
            return {"success": True, "description": cached, "cached": True}

    # Encode image
    image_data = encode_image_base64(image_path)
    if not image_data:
        return {"success": False, "error": "Failed to read image file"}

    # Build prompt based on mode
    if compact:
        # Compact mode: brief, actionable summary
        prompt = (
            "Describe this image in 2-3 concise sentences. "
            "Focus on: what type of image it is (screenshot, diagram, error, etc.), "
            "key visible text or error messages, and the main content. "
            "Be brief and factual."
        )
        if context:
            prompt += f" Context: {context}"
        max_tokens = 300
    else:
        # Full mode: detailed analysis
        prompt_parts = ["Analyze this image in detail."]
        if context:
            prompt_parts.append(f"Context: {context}")
        if include_text:
            prompt_parts.append("Transcribe ALL visible text exactly as shown.")
        if include_errors:
            prompt_parts.append("Identify any error messages, warnings, or issues visible.")
        prompt_parts.append("Describe the layout, UI elements, and any notable details.")
        prompt = " ".join(prompt_parts)
        max_tokens = 2000

    # Build API request
    mime_type = get_image_mime_type(image_path)
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3
    }

    try:
        response = requests.post(
            VISION_API_URL,
            json=payload,
            timeout=VISION_TIMEOUT
        )
        response.raise_for_status()

        data = response.json()
        description = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if description:
            cache_description(cache_key, description, image_path)
            return {"success": True, "description": description, "cached": False}
        else:
            return {"success": False, "error": "Empty response from vision model"}

    except requests.exceptions.Timeout:
        return {"success": False, "error": f"Vision model timeout after {VISION_TIMEOUT}s"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Vision API error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


def extract_image_paths(text: str) -> List[str]:
    """Extract potential image file paths from text.

    Looks for:
    - Absolute paths: /path/to/image.png
    - Relative paths: ./screenshots/image.png
    - Home paths: ~/screenshots/image.png
    """
    patterns = [
        # Absolute paths
        r'(/[^\s\'"<>|]+\.(?:png|jpg|jpeg|gif|webp|bmp|tiff))',
        # Relative paths with ./
        r'(\./[^\s\'"<>|]+\.(?:png|jpg|jpeg|gif|webp|bmp|tiff))',
        # Home directory paths
        r'(~/[^\s\'"<>|]+\.(?:png|jpg|jpeg|gif|webp|bmp|tiff))',
    ]

    paths = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Expand home directory
            expanded = os.path.expanduser(match)
            if os.path.exists(expanded):
                paths.append(expanded)

    return list(set(paths))  # Remove duplicates


def analyze_images_in_text(text: str, context: str = "") -> Dict[str, Any]:
    """Extract and analyze all images referenced in text.

    Args:
        text: Text that may contain image file paths
        context: Optional context for analysis

    Returns:
        Dict with 'images' list containing analysis results
    """
    paths = extract_image_paths(text)

    if not paths:
        return {
            "success": True,
            "images": [],
            "message": "No image paths found in text"
        }

    results = []
    for path in paths:
        analysis = analyze_image(path, context=context)
        results.append({
            "path": path,
            **analysis
        })

    return {
        "success": True,
        "images": results,
        "count": len(results)
    }


def preprocess_prompt(prompt: str, context: str = "", compact: bool = True) -> str:
    """Preprocess a prompt by analyzing and augmenting image references.

    This is the KEY FUNCTION for prompt augmentation (AC3).

    Given: "Check the error at /tmp/error.png"
    Returns: "Check the error at /tmp/error.png

    [IMAGE: /tmp/error.png]: Screenshot of a dashboard showing QA_FAILED error..."

    Args:
        prompt: Original user prompt that may contain image paths
        context: Optional context to help with analysis
        compact: Use compact (2-3 sentence) descriptions (default True)

    Returns:
        Augmented prompt with image descriptions appended
    """
    paths = extract_image_paths(prompt)

    if not paths:
        return prompt  # No images, return unchanged

    # Build augmentation blocks
    augmentations = []

    for path in paths:
        result = analyze_image(path, context=context, compact=compact)

        if result.get("success"):
            # Compact format for agent consumption
            augmentations.append(
                f"[IMAGE: {path}]: {result['description']}"
            )
        else:
            error = result.get("error", "Unknown error")
            augmentations.append(
                f"[IMAGE: {path}]: (failed to analyze - {error})"
            )

    # Combine original prompt with augmentations
    if augmentations:
        augmented = prompt + "\n\n" + "\n".join(augmentations)
        return augmented

    return prompt


def preprocess_prompt_inline(prompt: str, context: str = "") -> str:
    """Preprocess prompt with INLINE replacement of image paths.

    Alternative to preprocess_prompt - replaces the image path itself
    rather than appending descriptions at the end.

    Given: "Check the error at /tmp/error.png and fix it"
    Returns: "Check the error at [Image: /tmp/error.png - Dialog box showing 'Connection Failed'...] and fix it"

    This approach keeps the description in context where it's referenced.
    """
    paths = extract_image_paths(prompt)

    if not paths:
        return prompt

    result = prompt

    for path in paths:
        analysis = analyze_image(path, context=context)

        if analysis.get("success"):
            # Truncate description for inline use (first 200 chars)
            desc = analysis["description"][:200]
            if len(analysis["description"]) > 200:
                desc += "..."
            replacement = f"[Image: {path} - {desc}]"
        else:
            replacement = f"[Image not readable: {path}]"

        result = result.replace(path, replacement)

    return result


# =============================================================================
# MCP Server Protocol
# =============================================================================

def send_response(response: dict) -> None:
    """Send JSON-RPC response to stdout."""
    json_str = json.dumps(response)
    sys.stdout.write(json_str + "\n")
    sys.stdout.flush()


def handle_initialize(request_id: Any, params: dict) -> dict:
    """Handle MCP initialize request."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "vision-analyzer",
                "version": "1.0.0"
            }
        }
    }


def handle_list_tools(request_id: Any) -> dict:
    """Handle tools/list request."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "analyze_image",
                    "description": "Analyze a single image file using vision AI. Returns detailed description including visible text, errors, UI elements.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "image_path": {
                                "type": "string",
                                "description": "Absolute or relative path to the image file"
                            },
                            "context": {
                                "type": "string",
                                "description": "Optional context about what to look for in the image"
                            },
                            "include_text": {
                                "type": "boolean",
                                "description": "Whether to transcribe visible text (default: true)"
                            },
                            "include_errors": {
                                "type": "boolean",
                                "description": "Whether to identify error messages (default: true)"
                            }
                        },
                        "required": ["image_path"]
                    }
                },
                {
                    "name": "analyze_images_in_text",
                    "description": "Extract and analyze all image file paths found in a block of text. Useful for processing user messages that reference screenshots.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Text that may contain image file paths"
                            },
                            "context": {
                                "type": "string",
                                "description": "Optional context for analysis"
                            }
                        },
                        "required": ["text"]
                    }
                },
                {
                    "name": "extract_image_paths",
                    "description": "Extract image file paths from text without analyzing them. Returns list of valid image paths found.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Text to search for image paths"
                            }
                        },
                        "required": ["text"]
                    }
                },
                {
                    "name": "preprocess_prompt",
                    "description": "Preprocess a user prompt by detecting image paths, analyzing them with vision AI, and returning an augmented prompt with image descriptions appended. Use this to transparently add visual context to prompts.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "The user prompt that may contain image file paths"
                            },
                            "inline": {
                                "type": "boolean",
                                "description": "If true, replace paths inline instead of appending (default: false)"
                            }
                        },
                        "required": ["prompt"]
                    }
                }
            ]
        }
    }


def handle_call_tool(request_id: Any, params: dict) -> dict:
    """Handle tools/call request."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    try:
        if tool_name == "analyze_image":
            result = analyze_image(
                arguments.get("image_path", ""),
                context=arguments.get("context", ""),
                include_text=arguments.get("include_text", True),
                include_errors=arguments.get("include_errors", True)
            )
        elif tool_name == "analyze_images_in_text":
            result = analyze_images_in_text(
                arguments.get("text", ""),
                context=arguments.get("context", "")
            )
        elif tool_name == "extract_image_paths":
            paths = extract_image_paths(arguments.get("text", ""))
            result = {"paths": paths, "count": len(paths)}
        elif tool_name == "preprocess_prompt":
            prompt = arguments.get("prompt", "")
            inline = arguments.get("inline", False)
            if inline:
                augmented = preprocess_prompt_inline(prompt)
            else:
                augmented = preprocess_prompt(prompt)
            result = {"augmented_prompt": augmented, "original_prompt": prompt}
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": str(e)
            }
        }


def main():
    """Main MCP server loop."""
    # Log startup
    sys.stderr.write("Vision MCP Server starting...\n")
    sys.stderr.write(f"  Vision model: {VISION_MODEL}\n")
    sys.stderr.write(f"  API URL: {VISION_API_URL}\n")
    sys.stderr.write(f"  Cache dir: {CACHE_DIR}\n")
    sys.stderr.flush()

    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            method = request.get("method", "")
            request_id = request.get("id")
            params = request.get("params", {})

            if method == "initialize":
                response = handle_initialize(request_id, params)
            elif method == "tools/list":
                response = handle_list_tools(request_id)
            elif method == "tools/call":
                response = handle_call_tool(request_id, params)
            elif method == "notifications/initialized":
                continue  # Notification, no response needed
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            send_response(response)

        except json.JSONDecodeError as e:
            sys.stderr.write(f"JSON parse error: {e}\n")
            sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")
            sys.stderr.flush()


def cli_mode():
    """Command-line interface for direct usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Vision Image Analyzer - Analyze images using vision LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a single image
  %(prog)s /path/to/screenshot.png

  # Analyze with context
  %(prog)s /path/to/error.png --context "Error dialog from app startup"

  # Extract image paths from text
  %(prog)s --extract "Check the error at /tmp/error.png and /tmp/log.png"

  # Preprocess a prompt (augment with image descriptions)
  %(prog)s --preprocess "Check the error at /tmp/error.png"

  # Preprocess with inline replacement
  %(prog)s --preprocess "Check /tmp/error.png" --inline

  # Run as MCP server (for Goose integration)
  %(prog)s --mcp
        """
    )

    parser.add_argument("image_path", nargs="?", help="Path to image file to analyze")
    parser.add_argument("--context", "-c", help="Additional context for analysis")
    parser.add_argument("--extract", "-e", help="Extract and analyze image paths from text")
    parser.add_argument("--preprocess", "-p", help="Preprocess prompt: analyze images and augment text")
    parser.add_argument("--inline", action="store_true", help="Replace paths inline instead of appending")
    parser.add_argument("--paths-only", action="store_true", help="Only extract paths, don't analyze")
    parser.add_argument("--mcp", action="store_true", help="Run as MCP server")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.mcp:
        main()
        return

    if args.preprocess:
        if args.inline:
            augmented = preprocess_prompt_inline(args.preprocess, context=args.context or "")
        else:
            augmented = preprocess_prompt(args.preprocess, context=args.context or "")

        if args.json:
            print(json.dumps({
                "original": args.preprocess,
                "augmented": augmented
            }, indent=2))
        else:
            print(augmented)
        return

    if args.extract:
        if args.paths_only:
            paths = extract_image_paths(args.extract)
            if args.json:
                print(json.dumps({"paths": paths, "count": len(paths)}, indent=2))
            else:
                if paths:
                    print(f"Found {len(paths)} image(s):")
                    for p in paths:
                        print(f"  {p}")
                else:
                    print("No image paths found")
        else:
            result = analyze_images_in_text(args.extract, context=args.context or "")
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                if result.get("images"):
                    for img in result["images"]:
                        print(f"\n=== {img['path']} ===")
                        if img.get("success"):
                            print(img.get("description", "No description"))
                        else:
                            print(f"Error: {img.get('error')}")
                else:
                    print("No images found in text")
        return

    if not args.image_path:
        parser.print_help()
        return

    result = analyze_image(
        args.image_path,
        context=args.context or "",
        force_refresh=args.no_cache
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("success"):
            cached = " (cached)" if result.get("cached") else ""
            print(f"Analysis{cached}:\n")
            print(result.get("description", "No description"))
        else:
            print(f"Error: {result.get('error')}")


if __name__ == "__main__":
    import sys
    # If stdin is a tty, use CLI mode; otherwise MCP mode
    if sys.stdin.isatty() and len(sys.argv) > 1:
        cli_mode()
    elif len(sys.argv) > 1 and "--mcp" not in sys.argv:
        cli_mode()
    else:
        main()
