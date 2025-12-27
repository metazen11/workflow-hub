"""Tests for RoleConfig model - TDD Red Phase.

These tests define the expected behavior for the RoleConfig model
that stores agent roles and prompts in the database (not hardcoded).

Run: pytest tests/test_role_config.py -v

Expected: Tests FAIL initially (Red phase)
After WH-010 implementation: Tests PASS (Green phase)
"""
import pytest
import json


class TestRoleConfigModel:
    """Tests for RoleConfig SQLAlchemy model."""

    def test_role_config_model_exists(self, db_session):
        """RoleConfig model should be importable."""
        from app.models.role_config import RoleConfig
        assert RoleConfig is not None

    def test_role_config_has_required_fields(self, db_session):
        """RoleConfig should have all required fields."""
        from app.models.role_config import RoleConfig

        # Create a config to test fields
        config = RoleConfig(
            role="test_role",
            name="Test Role",
            description="A test role for testing",
            prompt="Test prompt content",
            checks={"test_check": True},
            requires_approval=False,
            active=True
        )

        assert config.role == "test_role"
        assert config.name == "Test Role"
        assert config.description == "A test role for testing"
        assert config.prompt == "Test prompt content"
        assert config.checks == {"test_check": True}
        assert config.requires_approval is False
        assert config.active is True

    def test_role_config_persists_to_database(self, db_session):
        """RoleConfig should save to and load from database."""
        from app.models.role_config import RoleConfig

        config = RoleConfig(
            role="persist_test",
            name="Persist Test",
            description="Testing persistence",
            prompt="Some prompt",
            checks={},
            requires_approval=False,
            active=True
        )

        db_session.add(config)
        db_session.commit()

        # Reload from database
        loaded = db_session.query(RoleConfig).filter(
            RoleConfig.role == "persist_test"
        ).first()

        assert loaded is not None
        assert loaded.name == "Persist Test"
        assert loaded.role == "persist_test"

        # Clean up test data
        db_session.delete(loaded)
        db_session.commit()

    def test_role_is_unique(self, db_session):
        """Each role should be unique in the database."""
        from app.models.role_config import RoleConfig
        from sqlalchemy.exc import IntegrityError

        config1 = RoleConfig(
            role="unique_role",
            name="First",
            prompt="Prompt 1"
        )
        db_session.add(config1)
        db_session.commit()

        config2 = RoleConfig(
            role="unique_role",  # Same role - should fail
            name="Second",
            prompt="Prompt 2"
        )
        db_session.add(config2)

        with pytest.raises(IntegrityError):
            db_session.commit()

        # Clean up - rollback removes config2, delete config1
        db_session.rollback()
        config1 = db_session.query(RoleConfig).filter(
            RoleConfig.role == "unique_role"
        ).first()
        if config1:
            db_session.delete(config1)
            db_session.commit()

    def test_role_config_to_dict(self, db_session):
        """RoleConfig should serialize to dictionary."""
        from app.models.role_config import RoleConfig

        config = RoleConfig(
            role="dict_test",
            name="Dict Test",
            description="Testing to_dict",
            prompt="Prompt content",
            checks={"rule1": "value1"},
            requires_approval=True,
            active=True
        )
        db_session.add(config)
        db_session.commit()

        data = config.to_dict()

        assert data["role"] == "dict_test"
        assert data["name"] == "Dict Test"
        assert data["description"] == "Testing to_dict"
        assert data["prompt"] == "Prompt content"
        assert data["checks"] == {"rule1": "value1"}
        assert data["requires_approval"] is True
        assert data["active"] is True
        assert "created_at" in data

        # Clean up test data
        db_session.delete(config)
        db_session.commit()


class TestAgentRoleEnum:
    """Tests for AgentRole enum including new roles."""

    def test_agent_role_has_director(self):
        """AgentRole enum should include DIRECTOR."""
        from app.models.report import AgentRole
        assert hasattr(AgentRole, "DIRECTOR")
        assert AgentRole.DIRECTOR.value == "director"

    def test_agent_role_has_docs(self):
        """AgentRole enum should include DOCS."""
        from app.models.report import AgentRole
        assert hasattr(AgentRole, "DOCS")
        assert AgentRole.DOCS.value == "docs"

    def test_agent_role_has_cicd(self):
        """AgentRole enum should include CICD."""
        from app.models.report import AgentRole
        assert hasattr(AgentRole, "CICD")
        assert AgentRole.CICD.value == "cicd"

    def test_all_agent_roles(self):
        """AgentRole should have all 7 roles."""
        from app.models.report import AgentRole

        expected_roles = {"director", "pm", "dev", "qa", "security", "docs", "cicd"}
        actual_roles = {role.value for role in AgentRole}

        assert expected_roles == actual_roles


class TestRoleConfigSeeding:
    """Tests that all agent roles have configurations in the database."""

    def test_all_roles_have_config(self, db_session):
        """Every AgentRole should have a corresponding RoleConfig entry."""
        from app.models.report import AgentRole
        from app.models.role_config import RoleConfig

        for role in AgentRole:
            config = db_session.query(RoleConfig).filter(
                RoleConfig.role == role.value
            ).first()

            assert config is not None, f"Missing RoleConfig for role: {role.value}"
            assert config.prompt, f"Empty prompt for role: {role.value}"
            assert config.name, f"Empty name for role: {role.value}"

    def test_director_has_checks(self, db_session):
        """Director role should have enforcement checks defined."""
        from app.models.role_config import RoleConfig

        director = db_session.query(RoleConfig).filter(
            RoleConfig.role == "director"
        ).first()

        assert director is not None, "Director role config not found"
        assert director.checks is not None, "Director should have checks"
        assert len(director.checks) > 0, "Director should have at least one check"

        # Verify expected check categories
        expected_checks = ["orm_usage", "workspace", "dry", "migrations", "tdd"]
        for check in expected_checks:
            assert check in director.checks, f"Director missing check: {check}"

    def test_cicd_requires_approval(self, db_session):
        """CICD role should require human approval."""
        from app.models.role_config import RoleConfig

        cicd = db_session.query(RoleConfig).filter(
            RoleConfig.role == "cicd"
        ).first()

        assert cicd is not None, "CICD role config not found"
        assert cicd.requires_approval is True, "CICD should require approval"


class TestPromptValidation:
    """Tests that prompts have required content."""

    # Official roles that should be validated
    OFFICIAL_ROLES = ("director", "pm", "dev", "qa", "security", "docs", "cicd")

    def test_prompts_are_not_empty(self, db_session):
        """All role prompts should have content."""
        from app.models.role_config import RoleConfig

        configs = db_session.query(RoleConfig).filter(
            RoleConfig.active == True,
            RoleConfig.role.in_(self.OFFICIAL_ROLES)
        ).all()

        for config in configs:
            assert config.prompt, f"Empty prompt for: {config.role}"
            assert len(config.prompt) > 50, f"Prompt too short for: {config.role}"

    def test_prompts_have_role_section(self, db_session):
        """Prompts should describe the agent's role."""
        from app.models.role_config import RoleConfig

        configs = db_session.query(RoleConfig).filter(
            RoleConfig.active == True,
            RoleConfig.role.in_(self.OFFICIAL_ROLES)
        ).all()

        for config in configs:
            prompt_lower = config.prompt.lower()
            has_role_section = (
                "your role" in prompt_lower or
                "your task" in prompt_lower or
                "you are" in prompt_lower or
                f"## {config.role}" in prompt_lower
            )
            assert has_role_section, f"Prompt missing role section for: {config.role}"

    def test_prompts_have_output_format(self, db_session):
        """Prompts should specify expected output format."""
        from app.models.role_config import RoleConfig

        # Skip director - it's a supervisor, not output producer
        configs = db_session.query(RoleConfig).filter(
            RoleConfig.active == True,
            RoleConfig.role.in_(self.OFFICIAL_ROLES),
            RoleConfig.role != "director"
        ).all()

        for config in configs:
            prompt_lower = config.prompt.lower()
            has_output_section = (
                "output" in prompt_lower or
                "json" in prompt_lower or
                "format" in prompt_lower or
                "report" in prompt_lower
            )
            assert has_output_section, f"Prompt missing output format for: {config.role}"


class TestDirectorChecks:
    """Tests for Director enforcement rules."""

    def test_director_checks_are_valid_json(self, db_session):
        """Director checks should be valid JSON structure."""
        from app.models.role_config import RoleConfig

        director = db_session.query(RoleConfig).filter(
            RoleConfig.role == "director"
        ).first()

        assert director is not None
        checks = director.checks

        # Should be a dict
        assert isinstance(checks, dict)

        # Each check should have description
        for check_name, check_config in checks.items():
            assert "description" in check_config, f"Check {check_name} missing description"

    def test_orm_usage_check_exists(self, db_session):
        """Director should have ORM usage check."""
        from app.models.role_config import RoleConfig

        director = db_session.query(RoleConfig).filter(
            RoleConfig.role == "director"
        ).first()

        assert "orm_usage" in director.checks
        orm_check = director.checks["orm_usage"]

        assert "description" in orm_check
        assert "patterns_to_reject" in orm_check or "reject" in orm_check

    def test_tdd_check_exists(self, db_session):
        """Director should have TDD enforcement check."""
        from app.models.role_config import RoleConfig

        director = db_session.query(RoleConfig).filter(
            RoleConfig.role == "director"
        ).first()

        assert "tdd" in director.checks
        tdd_check = director.checks["tdd"]

        assert "description" in tdd_check
