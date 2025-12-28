"""Tests for the deployment service."""
import pytest
from unittest.mock import patch, MagicMock
from app.models.deployment_history import DeploymentHistory, DeploymentStatus
from app.services.deployment_service import DeploymentService


def test_deployment_history_model():
    """Test DeploymentHistory model creation."""
    deployment = DeploymentHistory(
        run_id=1,
        environment_id=1,
        commit_sha="abc123",
        status=DeploymentStatus.PENDING
    )
    assert deployment.run_id == 1
    assert deployment.environment_id == 1
    assert deployment.status == DeploymentStatus.PENDING


def test_deployment_history_to_dict():
    """Test DeploymentHistory to_dict method."""
    deployment = DeploymentHistory(
        id=1,
        run_id=1,
        environment_id=1,
        commit_sha="abc123def456789012345678901234567890abcd",
        status=DeploymentStatus.DEPLOYED,
        is_rollback=False
    )
    result = deployment.to_dict()
    assert result["id"] == 1
    assert result["run_id"] == 1
    assert result["commit_sha"] == "abc123def456789012345678901234567890abcd"
    assert result["status"] == "deployed"
    assert result["is_rollback"] is False


def test_deployment_service_init(db_session):
    """Test DeploymentService initialization."""
    service = DeploymentService(db_session)
    assert service.db == db_session


def test_get_environment_none(db_session):
    """Test get_environment returns None when no environment exists."""
    service = DeploymentService(db_session)
    result = service.get_environment(project_id=9999)
    assert result is None


def test_start_deployment_run_not_found(db_session):
    """Test start_deployment with non-existent run."""
    service = DeploymentService(db_session)
    deployment, error = service.start_deployment(
        run_id=9999,
        environment_id=1
    )
    assert deployment is None
    assert error == "Run not found"


def test_start_deployment_environment_not_found(db_session, sample_project, sample_run):
    """Test start_deployment with non-existent environment."""
    service = DeploymentService(db_session)
    deployment, error = service.start_deployment(
        run_id=sample_run.id,
        environment_id=9999
    )
    assert deployment is None
    assert error == "Environment not found"


def test_rollback_deployment_not_found(db_session):
    """Test rollback with non-existent deployment."""
    service = DeploymentService(db_session)
    result, error = service.rollback(deployment_id=9999, reason="Test")
    assert result is None
    assert error == "Deployment not found"


def test_run_health_check_no_url(db_session, sample_project, sample_run):
    """Test health check when no URL is configured."""
    from app.models.environment import Environment, EnvironmentType

    # Create environment without health check URL
    environment = Environment(
        project_id=sample_project.id,
        name="Test Env",
        env_type=EnvironmentType.TESTING,
        deploy_command="echo 'deploy'"
    )
    db_session.add(environment)
    db_session.commit()

    service = DeploymentService(db_session)

    # Start deployment
    deployment, error = service.start_deployment(
        run_id=sample_run.id,
        environment_id=environment.id
    )
    assert deployment is not None
    assert error is None

    # Health check should pass when no URL is configured
    passed, response = service.run_health_check(deployment.id)
    assert passed is True
    assert response["message"] == "No health check configured"


def test_deployment_status_enum():
    """Test DeploymentStatus enum values."""
    assert DeploymentStatus.PENDING.value == "pending"
    assert DeploymentStatus.DEPLOYING.value == "deploying"
    assert DeploymentStatus.DEPLOYED.value == "deployed"
    assert DeploymentStatus.FAILED.value == "failed"
    assert DeploymentStatus.ROLLED_BACK.value == "rolled_back"


@patch('subprocess.run')
def test_execute_deployment_success(mock_subprocess, db_session, sample_project, sample_run):
    """Test successful deployment execution."""
    from app.models.environment import Environment, EnvironmentType

    # Create environment with deploy command
    environment = Environment(
        project_id=sample_project.id,
        name="Test Env",
        env_type=EnvironmentType.TESTING,
        deploy_command="echo 'deploy'"
    )
    db_session.add(environment)
    db_session.commit()

    # Mock subprocess success
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Deployment successful"
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    service = DeploymentService(db_session)

    # Start deployment
    deployment, _ = service.start_deployment(
        run_id=sample_run.id,
        environment_id=environment.id
    )

    # Execute deployment
    success, output = service.execute_deployment(deployment.id)

    assert success is True
    assert "Deployment successful" in output

    # Verify deployment status updated
    db_session.refresh(deployment)
    assert deployment.status == DeploymentStatus.DEPLOYED


@patch('subprocess.run')
def test_execute_deployment_failure(mock_subprocess, db_session, sample_project, sample_run):
    """Test failed deployment execution."""
    from app.models.environment import Environment, EnvironmentType

    # Create environment
    environment = Environment(
        project_id=sample_project.id,
        name="Test Env",
        env_type=EnvironmentType.TESTING,
        deploy_command="exit 1"
    )
    db_session.add(environment)
    db_session.commit()

    # Mock subprocess failure
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Deployment failed"
    mock_subprocess.return_value = mock_result

    service = DeploymentService(db_session)

    # Start deployment
    deployment, _ = service.start_deployment(
        run_id=sample_run.id,
        environment_id=environment.id
    )

    # Execute deployment
    success, output = service.execute_deployment(deployment.id)

    assert success is False

    # Verify deployment status updated
    db_session.refresh(deployment)
    assert deployment.status == DeploymentStatus.FAILED


def test_get_deployment_history(db_session, sample_project, sample_run):
    """Test getting deployment history."""
    from app.models.environment import Environment, EnvironmentType

    # Create environment
    environment = Environment(
        project_id=sample_project.id,
        name="Test Env",
        env_type=EnvironmentType.TESTING,
        deploy_command="echo test"
    )
    db_session.add(environment)
    db_session.commit()

    # Create some deployments
    for i in range(3):
        deployment = DeploymentHistory(
            run_id=sample_run.id,
            environment_id=environment.id,
            commit_sha=f"commit_{i}",
            status=DeploymentStatus.DEPLOYED
        )
        db_session.add(deployment)
    db_session.commit()

    service = DeploymentService(db_session)
    history = service.get_deployment_history(run_id=sample_run.id)

    assert len(history) == 3
