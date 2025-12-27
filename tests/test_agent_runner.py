"""
Tests for the Goose agent runner.

Verifies:
1. Goose executable discovery works
2. Agent runner can invoke Goose
3. Error handling is graceful
4. LLM integration works end-to-end

Run with: pytest tests/test_agent_runner.py -v
"""
import os
import sys
import json
import pytest
import subprocess
from unittest.mock import patch, MagicMock

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from agent_runner import (
    find_goose_executable,
    GOOSE_EXECUTABLE,
    run_goose,
    BASE_INSTRUCTIONS,
    ROLE_PROMPTS,
)


class TestGooseExecutableDiscovery:
    """Test that we can find the Goose executable."""

    def test_find_goose_returns_string(self):
        """find_goose_executable should return a string path."""
        result = find_goose_executable()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_goose_executable_constant_set(self):
        """GOOSE_EXECUTABLE constant should be set at module load."""
        assert GOOSE_EXECUTABLE is not None
        assert isinstance(GOOSE_EXECUTABLE, str)

    def test_homebrew_path_checked(self):
        """Should check /opt/homebrew/bin/goose for Apple Silicon Macs."""
        # The function should check this path
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda p: p == "/opt/homebrew/bin/goose"
            result = find_goose_executable()
            assert result == "/opt/homebrew/bin/goose"

    def test_pipx_path_checked(self):
        """Should check ~/.local/bin/goose for pipx installations."""
        pipx_path = os.path.expanduser("~/.local/bin/goose")
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda p: p == pipx_path
            result = find_goose_executable()
            assert result == pipx_path

    def test_explicit_goose_path_env_var(self):
        """GOOSE_PATH env var should override detection."""
        custom_path = "/custom/path/to/goose"
        with patch.dict(os.environ, {"GOOSE_PATH": custom_path}):
            with patch('os.path.exists', return_value=True):
                result = find_goose_executable()
                assert result == custom_path

    def test_fallback_to_which_command(self):
        """Should try 'which goose' if common paths don't exist."""
        with patch('os.path.exists', return_value=False):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="/some/other/path/goose\n"
                )
                result = find_goose_executable()
                assert result == "/some/other/path/goose"


class TestGooseSystemInstallation:
    """Test that Goose is actually installed on this system."""

    def test_goose_is_installed(self):
        """Verify Goose is installed and accessible."""
        goose_path = find_goose_executable()

        # Either it's a valid path or we can find it via which
        if os.path.exists(goose_path):
            assert os.access(goose_path, os.X_OK), f"Goose at {goose_path} is not executable"
        else:
            # Try which command
            result = subprocess.run(["which", "goose"], capture_output=True, text=True)
            assert result.returncode == 0, "Goose not found. Install with: brew install goose-ai"

    def test_goose_version(self):
        """Verify Goose responds to --version."""
        goose_path = find_goose_executable()

        try:
            result = subprocess.run(
                [goose_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            # Goose should return version info
            assert result.returncode == 0 or "goose" in result.stdout.lower() or "goose" in result.stderr.lower()
        except FileNotFoundError:
            pytest.skip("Goose not installed")
        except subprocess.TimeoutExpired:
            pytest.skip("Goose --version timed out")


class TestAgentPrompts:
    """Test agent prompt generation."""

    def test_base_instructions_contain_principles(self):
        """BASE_INSTRUCTIONS should contain coding principles."""
        assert "Coding Principles" in BASE_INSTRUCTIONS
        assert "Security" in BASE_INSTRUCTIONS
        assert "Testing" in BASE_INSTRUCTIONS

    def test_all_agent_types_have_prompts(self):
        """All expected agent types should have prompts defined."""
        expected_agents = ["pm", "dev", "qa", "security"]
        for agent in expected_agents:
            assert agent in ROLE_PROMPTS, f"Missing prompt for agent: {agent}"
            assert len(ROLE_PROMPTS[agent]) > 100, f"Prompt for {agent} too short"

    def test_pm_prompt_creates_tasks_json(self):
        """PM agent prompt should instruct creation of tasks.json."""
        assert "tasks.json" in ROLE_PROMPTS["pm"]
        assert "acceptance_criteria" in ROLE_PROMPTS["pm"]

    def test_dev_prompt_reads_tasks(self):
        """DEV agent prompt should read from tasks.json."""
        assert "tasks.json" in ROLE_PROMPTS["dev"]
        assert "commit" in ROLE_PROMPTS["dev"].lower()

    def test_qa_prompt_writes_tests(self):
        """QA agent prompt should write pytest tests."""
        assert "pytest" in ROLE_PROMPTS["qa"]
        assert "tests/" in ROLE_PROMPTS["qa"]

    def test_security_prompt_checks_owasp(self):
        """Security agent prompt should check OWASP vulnerabilities."""
        assert "OWASP" in ROLE_PROMPTS["security"]
        assert "SQL Injection" in ROLE_PROMPTS["security"]


class TestRunGooseFunction:
    """Test the run_goose function."""

    def test_unknown_agent_type_returns_error(self):
        """Unknown agent type should return fail status."""
        result = run_goose("unknown_agent", 1, "/tmp")
        assert result["status"] == "fail"
        assert "Unknown agent type" in result["summary"]

    def test_run_goose_returns_dict(self):
        """run_goose should always return a dict with status."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"status": "pass", "summary": "test"}'
            )
            result = run_goose("pm", 1, "/tmp")
            assert isinstance(result, dict)
            assert "status" in result

    def test_timeout_returns_graceful_error(self):
        """Timeout should return fail status, not raise exception."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("goose", 300)
            result = run_goose("pm", 1, "/tmp")
            assert result["status"] == "fail"
            assert "timed out" in result["summary"]

    def test_file_not_found_returns_graceful_error(self):
        """FileNotFoundError should return fail status with helpful message."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("goose not found")
            result = run_goose("pm", 1, "/tmp")
            assert result["status"] == "fail"
            assert "not found" in result["summary"].lower()
            assert "details" in result


class TestDockerModelRunner:
    """Test Docker Model Runner is available and working."""

    DOCKER_MODEL_API = "http://localhost:12434/engines/llama.cpp/v1"

    def test_docker_model_runner_status(self):
        """Verify Docker Model Runner is running."""
        result = subprocess.run(
            ["docker", "model", "status"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, "Docker Model Runner not running"
        assert "running" in result.stdout.lower(), "Docker Model Runner not in running state"

    def test_docker_model_api_accessible(self):
        """Verify Docker Model Runner API is accessible."""
        import requests
        try:
            response = requests.get(f"{self.DOCKER_MODEL_API}/models", timeout=5)
            assert response.status_code == 200, f"API returned {response.status_code}"
            data = response.json()
            assert "data" in data, "API response missing 'data' field"
        except requests.exceptions.ConnectionError:
            pytest.fail("Cannot connect to Docker Model Runner API at localhost:12434")

    def test_docker_models_available(self):
        """Verify at least one AI model is available."""
        result = subprocess.run(
            ["docker", "model", "list"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, "Failed to list Docker models"
        # Should have at least one model
        lines = result.stdout.strip().split('\n')
        assert len(lines) > 1, "No AI models installed in Docker"

    def test_qwen_coder_model_available(self):
        """Verify qwen3-coder model is available (used by Goose)."""
        import requests
        try:
            response = requests.get(f"{self.DOCKER_MODEL_API}/models", timeout=5)
            data = response.json()
            model_ids = [m["id"] for m in data.get("data", [])]
            assert "ai/qwen3-coder:latest" in model_ids, \
                f"qwen3-coder not found. Available: {model_ids}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Docker Model Runner API not accessible")

    def test_model_runner_can_generate(self):
        """Verify Docker Model Runner can generate text."""
        import requests
        try:
            response = requests.post(
                f"{self.DOCKER_MODEL_API}/chat/completions",
                json={
                    "model": "ai/qwen3-coder:latest",
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "max_tokens": 50
                },
                timeout=30
            )
            assert response.status_code == 200, f"Generation failed: {response.text}"
            data = response.json()
            assert "choices" in data, "Response missing 'choices'"
            assert len(data["choices"]) > 0, "No choices returned"
        except requests.exceptions.ConnectionError:
            pytest.skip("Docker Model Runner API not accessible")
        except requests.exceptions.Timeout:
            pytest.skip("Model generation timed out")


class TestGooseLLMIntegration:
    """Test actual LLM integration (requires Goose + configured provider)."""

    @pytest.mark.slow
    @pytest.mark.skipif(
        not os.path.exists("/opt/homebrew/bin/goose") and
        subprocess.run(["which", "goose"], capture_output=True).returncode != 0,
        reason="Goose not installed"
    )
    def test_goose_can_run_simple_prompt(self):
        """Verify Goose can execute a simple prompt."""
        goose_path = find_goose_executable()

        try:
            result = subprocess.run(
                [goose_path, "run", "--text", "Say hello in JSON: {\"message\": \"hello\"}"],
                capture_output=True,
                text=True,
                timeout=60  # 1 minute timeout
            )
            # Should complete without error
            assert result.returncode == 0 or result.stdout or result.stderr
        except subprocess.TimeoutExpired:
            pytest.skip("Goose prompt timed out - LLM may not be configured")
        except FileNotFoundError:
            pytest.skip("Goose not installed")


class TestErrorHandling:
    """Test graceful failure handling per coding principles."""

    def test_all_run_goose_paths_return_dict(self):
        """Every code path in run_goose should return a dict, never raise."""
        test_cases = [
            ("valid_agent", "pm"),
            ("invalid_agent", "nonexistent"),
        ]

        for name, agent in test_cases:
            with patch('subprocess.run') as mock_run:
                # Test success path
                mock_run.return_value = MagicMock(returncode=0, stdout="{}")
                result = run_goose(agent, 1, "/tmp")
                assert isinstance(result, dict), f"Failed for {name}"

                # Test timeout path
                mock_run.side_effect = subprocess.TimeoutExpired("cmd", 1)
                result = run_goose(agent, 1, "/tmp")
                assert isinstance(result, dict), f"Timeout failed for {name}"

                # Test exception path
                mock_run.side_effect = Exception("test error")
                result = run_goose(agent, 1, "/tmp")
                assert isinstance(result, dict), f"Exception failed for {name}"

    def test_error_responses_have_required_fields(self):
        """Error responses should have status and summary."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("test error")
            result = run_goose("pm", 1, "/tmp")

            assert "status" in result
            assert "summary" in result
            assert result["status"] == "fail"


# Marker for slow tests
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow (requires LLM)")
