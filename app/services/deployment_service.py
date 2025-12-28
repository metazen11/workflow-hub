"""Deployment service for managing deployments and rollbacks."""
import os
import subprocess
import requests
from datetime import datetime, timezone
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session

from app.models.run import Run, RunState
from app.models.project import Project
from app.models.environment import Environment
from app.models.deployment_history import DeploymentHistory, DeploymentStatus
from app.models.audit import log_event
from app.services.webhook_service import dispatch_webhook, EVENT_STATE_CHANGE


class DeploymentService:
    """Service for managing deployments, health checks, and rollbacks."""

    def __init__(self, db: Session):
        self.db = db

    def get_environment(self, project_id: int) -> Optional[Environment]:
        """Get the active environment for a project."""
        return (
            self.db.query(Environment)
            .filter(Environment.project_id == project_id, Environment.is_active == True)
            .first()
        )

    def get_latest_deployment(self, environment_id: int) -> Optional[DeploymentHistory]:
        """Get the most recent successful deployment for an environment."""
        return (
            self.db.query(DeploymentHistory)
            .filter(
                DeploymentHistory.environment_id == environment_id,
                DeploymentHistory.status == DeploymentStatus.DEPLOYED
            )
            .order_by(DeploymentHistory.completed_at.desc())
            .first()
        )

    def get_previous_deployment(self, deployment_id: int) -> Optional[DeploymentHistory]:
        """Get the deployment before the specified one (for rollback)."""
        current = self.db.query(DeploymentHistory).filter(
            DeploymentHistory.id == deployment_id
        ).first()

        if not current:
            return None

        return (
            self.db.query(DeploymentHistory)
            .filter(
                DeploymentHistory.environment_id == current.environment_id,
                DeploymentHistory.status == DeploymentStatus.DEPLOYED,
                DeploymentHistory.id < deployment_id
            )
            .order_by(DeploymentHistory.completed_at.desc())
            .first()
        )

    def start_deployment(
        self,
        run_id: int,
        environment_id: int,
        approved_by: str = None,
        triggered_by: str = "agent"
    ) -> Tuple[Optional[DeploymentHistory], Optional[str]]:
        """Start a new deployment.

        Creates a deployment history record and initiates deployment.
        Returns (deployment, error_message).
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return None, "Run not found"

        environment = self.db.query(Environment).filter(Environment.id == environment_id).first()
        if not environment:
            return None, "Environment not found"

        if not environment.deploy_command:
            return None, "No deploy command configured for environment"

        # Get git commit SHA from project repo
        project = self.db.query(Project).filter(Project.id == run.project_id).first()
        commit_sha = self._get_current_commit(project.repo_path if project else None)

        # Get previous deployment for rollback reference
        latest = self.get_latest_deployment(environment_id)
        previous_sha = latest.commit_sha if latest else None

        # Create deployment record
        deployment = DeploymentHistory(
            run_id=run_id,
            environment_id=environment_id,
            commit_sha=commit_sha,
            previous_commit_sha=previous_sha,
            status=DeploymentStatus.DEPLOYING,
            deploy_command_used=environment.deploy_command,
            triggered_by=triggered_by,
            approved_by=approved_by
        )
        self.db.add(deployment)
        self.db.commit()
        self.db.refresh(deployment)

        log_event(
            self.db,
            actor=triggered_by,
            action="start_deployment",
            entity_type="deployment",
            entity_id=deployment.id,
            details={
                "run_id": run_id,
                "environment_id": environment_id,
                "commit_sha": commit_sha
            }
        )

        return deployment, None

    def execute_deployment(self, deployment_id: int) -> Tuple[bool, str]:
        """Execute the actual deployment command.

        Returns (success, output/error).
        """
        deployment = self.db.query(DeploymentHistory).filter(
            DeploymentHistory.id == deployment_id
        ).first()

        if not deployment:
            return False, "Deployment not found"

        environment = self.db.query(Environment).filter(
            Environment.id == deployment.environment_id
        ).first()

        if not environment:
            return False, "Environment not found"

        project = self.db.query(Project).filter(
            Project.id == self.db.query(Run).filter(Run.id == deployment.run_id).first().project_id
        ).first()

        # Execute deployment command
        try:
            result = subprocess.run(
                deployment.deploy_command_used,
                shell=True,
                cwd=project.repo_path if project and project.repo_path else None,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            deployment.deploy_output = result.stdout + result.stderr

            if result.returncode == 0:
                deployment.status = DeploymentStatus.DEPLOYED
                deployment.completed_at = datetime.now(timezone.utc)

                # Update environment timestamps
                environment.last_deploy_at = datetime.now(timezone.utc)

                self.db.commit()

                log_event(
                    self.db,
                    actor="agent",
                    action="deploy_success",
                    entity_type="deployment",
                    entity_id=deployment_id,
                    details={"output_length": len(deployment.deploy_output)}
                )

                return True, deployment.deploy_output
            else:
                deployment.status = DeploymentStatus.FAILED
                deployment.completed_at = datetime.now(timezone.utc)
                self.db.commit()

                log_event(
                    self.db,
                    actor="agent",
                    action="deploy_failed",
                    entity_type="deployment",
                    entity_id=deployment_id,
                    details={"exit_code": result.returncode}
                )

                return False, f"Deploy command failed: {deployment.deploy_output}"

        except subprocess.TimeoutExpired:
            deployment.status = DeploymentStatus.FAILED
            deployment.deploy_output = "Deployment timed out after 5 minutes"
            deployment.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return False, "Deployment timed out"

        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.deploy_output = str(e)
            deployment.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return False, str(e)

    def run_health_check(self, deployment_id: int) -> Tuple[bool, dict]:
        """Run health check for a deployment.

        Returns (passed, response_data).
        """
        deployment = self.db.query(DeploymentHistory).filter(
            DeploymentHistory.id == deployment_id
        ).first()

        if not deployment:
            return False, {"error": "Deployment not found"}

        environment = self.db.query(Environment).filter(
            Environment.id == deployment.environment_id
        ).first()

        if not environment or not environment.health_check_url:
            # No health check configured, assume success
            deployment.health_check_passed = True
            deployment.health_check_at = datetime.now(timezone.utc)
            self.db.commit()
            return True, {"message": "No health check configured"}

        try:
            response = requests.get(
                environment.health_check_url,
                timeout=30,
                verify=True
            )

            response_data = {
                "status_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000,
                "url": environment.health_check_url
            }

            # Try to parse JSON response
            try:
                response_data["body"] = response.json()
            except Exception:
                response_data["body"] = response.text[:500]  # Truncate large responses

            passed = 200 <= response.status_code < 300

            deployment.health_check_passed = passed
            deployment.health_check_response = response_data
            deployment.health_check_at = datetime.now(timezone.utc)
            environment.last_health_check_at = datetime.now(timezone.utc)
            environment.is_healthy = passed
            self.db.commit()

            log_event(
                self.db,
                actor="agent",
                action="health_check",
                entity_type="deployment",
                entity_id=deployment_id,
                details={"passed": passed, "status_code": response.status_code}
            )

            return passed, response_data

        except requests.RequestException as e:
            error_data = {"error": str(e), "url": environment.health_check_url}

            deployment.health_check_passed = False
            deployment.health_check_response = error_data
            deployment.health_check_at = datetime.now(timezone.utc)
            environment.is_healthy = False
            self.db.commit()

            return False, error_data

    def run_test_suite(self, deployment_id: int) -> Tuple[bool, str]:
        """Run the test suite for a deployment.

        Returns (passed, output).
        """
        deployment = self.db.query(DeploymentHistory).filter(
            DeploymentHistory.id == deployment_id
        ).first()

        if not deployment:
            return False, "Deployment not found"

        environment = self.db.query(Environment).filter(
            Environment.id == deployment.environment_id
        ).first()

        if not environment or not environment.test_command:
            # No test command configured
            deployment.test_passed = True
            deployment.test_at = datetime.now(timezone.utc)
            self.db.commit()
            return True, "No test command configured"

        run = self.db.query(Run).filter(Run.id == deployment.run_id).first()
        project = self.db.query(Project).filter(Project.id == run.project_id).first() if run else None

        try:
            result = subprocess.run(
                environment.test_command,
                shell=True,
                cwd=project.repo_path if project and project.repo_path else None,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for tests
            )

            deployment.test_command_used = environment.test_command
            deployment.test_output = result.stdout + result.stderr
            deployment.test_passed = result.returncode == 0
            deployment.test_at = datetime.now(timezone.utc)
            self.db.commit()

            log_event(
                self.db,
                actor="agent",
                action="run_tests",
                entity_type="deployment",
                entity_id=deployment_id,
                details={"passed": deployment.test_passed, "exit_code": result.returncode}
            )

            return deployment.test_passed, deployment.test_output

        except subprocess.TimeoutExpired:
            deployment.test_passed = False
            deployment.test_output = "Tests timed out after 10 minutes"
            deployment.test_at = datetime.now(timezone.utc)
            self.db.commit()
            return False, "Tests timed out"

        except Exception as e:
            deployment.test_passed = False
            deployment.test_output = str(e)
            deployment.test_at = datetime.now(timezone.utc)
            self.db.commit()
            return False, str(e)

    def rollback(
        self,
        deployment_id: int,
        reason: str = None,
        triggered_by: str = "auto",
        target_deployment_id: int = None
    ) -> Tuple[Optional[DeploymentHistory], Optional[str]]:
        """Rollback to a previous deployment.

        Args:
            deployment_id: The failed deployment to rollback from
            reason: Reason for rollback
            triggered_by: "auto" or "human"
            target_deployment_id: Specific deployment to rollback to (optional)

        Returns (new_deployment, error_message).
        """
        current = self.db.query(DeploymentHistory).filter(
            DeploymentHistory.id == deployment_id
        ).first()

        if not current:
            return None, "Deployment not found"

        # Find target deployment to rollback to
        if target_deployment_id:
            target = self.db.query(DeploymentHistory).filter(
                DeploymentHistory.id == target_deployment_id
            ).first()
        else:
            target = self.get_previous_deployment(deployment_id)

        if not target:
            return None, "No previous deployment to rollback to"

        environment = self.db.query(Environment).filter(
            Environment.id == current.environment_id
        ).first()

        if not environment:
            return None, "Environment not found"

        # Get rollback command or use git checkout
        rollback_cmd = environment.rollback_command
        if not rollback_cmd and target.commit_sha:
            # Default to git checkout if no custom rollback command
            rollback_cmd = f"git checkout {target.commit_sha}"

        if not rollback_cmd:
            return None, "No rollback command and no target commit SHA"

        # Substitute placeholders in rollback command
        rollback_cmd = rollback_cmd.format(
            commit_sha=target.commit_sha or "",
            version=target.version or "",
            previous_sha=current.commit_sha or ""
        )

        # Create rollback deployment record
        rollback_deployment = DeploymentHistory(
            run_id=current.run_id,
            environment_id=current.environment_id,
            commit_sha=target.commit_sha,
            previous_commit_sha=current.commit_sha,
            status=DeploymentStatus.DEPLOYING,
            deploy_command_used=rollback_cmd,
            is_rollback=True,
            rolled_back_from_id=deployment_id,
            rolled_back_to_id=target.id,
            rollback_reason=reason,
            triggered_by=triggered_by
        )
        self.db.add(rollback_deployment)

        # Mark current deployment as rolled back
        current.status = DeploymentStatus.ROLLED_BACK
        self.db.commit()
        self.db.refresh(rollback_deployment)

        log_event(
            self.db,
            actor=triggered_by,
            action="rollback",
            entity_type="deployment",
            entity_id=rollback_deployment.id,
            details={
                "from_deployment": deployment_id,
                "to_deployment": target.id,
                "reason": reason
            }
        )

        return rollback_deployment, None

    def auto_rollback_on_failure(self, deployment_id: int) -> Tuple[bool, str]:
        """Automatically rollback if health check or tests fail.

        Returns (rollback_triggered, message).
        """
        deployment = self.db.query(DeploymentHistory).filter(
            DeploymentHistory.id == deployment_id
        ).first()

        if not deployment:
            return False, "Deployment not found"

        # Check if rollback is needed
        needs_rollback = False
        reason = None

        if deployment.health_check_passed is False:
            needs_rollback = True
            reason = "Health check failed"
        elif deployment.test_passed is False:
            needs_rollback = True
            reason = "Tests failed"

        if not needs_rollback:
            return False, "No rollback needed"

        # Perform rollback
        rollback_deployment, error = self.rollback(
            deployment_id=deployment_id,
            reason=reason,
            triggered_by="auto"
        )

        if error:
            return False, f"Rollback failed: {error}"

        # Execute the rollback deployment
        success, output = self.execute_deployment(rollback_deployment.id)

        if success:
            # Verify health after rollback
            health_passed, _ = self.run_health_check(rollback_deployment.id)
            if health_passed:
                return True, f"Auto-rollback successful: {reason}"
            else:
                return True, f"Auto-rollback completed but health check failed"
        else:
            return True, f"Auto-rollback triggered but execution failed: {output}"

    def get_deployment_history(
        self,
        environment_id: int = None,
        run_id: int = None,
        limit: int = 20
    ) -> List[DeploymentHistory]:
        """Get deployment history with optional filters."""
        query = self.db.query(DeploymentHistory)

        if environment_id:
            query = query.filter(DeploymentHistory.environment_id == environment_id)

        if run_id:
            query = query.filter(DeploymentHistory.run_id == run_id)

        return query.order_by(DeploymentHistory.created_at.desc()).limit(limit).all()

    def _get_current_commit(self, repo_path: str) -> Optional[str]:
        """Get current git commit SHA from repository."""
        if not repo_path or not os.path.exists(repo_path):
            return None

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return None

    def complete_deployment_flow(
        self,
        run_id: int,
        environment_id: int,
        approved_by: str = None
    ) -> Tuple[bool, dict]:
        """Execute complete deployment flow with health check and tests.

        Returns (success, result_dict).
        """
        result = {
            "deployment_id": None,
            "deploy_success": False,
            "health_check_passed": None,
            "tests_passed": None,
            "rollback_triggered": False,
            "final_status": None,
            "messages": []
        }

        # Start deployment
        deployment, error = self.start_deployment(
            run_id=run_id,
            environment_id=environment_id,
            approved_by=approved_by,
            triggered_by="agent"
        )

        if error:
            result["messages"].append(f"Failed to start deployment: {error}")
            result["final_status"] = "failed"
            return False, result

        result["deployment_id"] = deployment.id

        # Execute deployment
        success, output = self.execute_deployment(deployment.id)
        result["deploy_success"] = success

        if not success:
            result["messages"].append(f"Deployment failed: {output[:500]}")
            result["final_status"] = "failed"
            return False, result

        result["messages"].append("Deployment successful")

        # Run health check
        health_passed, health_data = self.run_health_check(deployment.id)
        result["health_check_passed"] = health_passed

        if not health_passed:
            result["messages"].append(f"Health check failed: {health_data}")

            # Trigger auto-rollback
            rollback_triggered, rollback_msg = self.auto_rollback_on_failure(deployment.id)
            result["rollback_triggered"] = rollback_triggered
            result["messages"].append(rollback_msg)
            result["final_status"] = "rolled_back"
            return False, result

        result["messages"].append("Health check passed")

        # Run test suite
        tests_passed, test_output = self.run_test_suite(deployment.id)
        result["tests_passed"] = tests_passed

        if not tests_passed:
            result["messages"].append(f"Tests failed")

            # Trigger auto-rollback
            rollback_triggered, rollback_msg = self.auto_rollback_on_failure(deployment.id)
            result["rollback_triggered"] = rollback_triggered
            result["messages"].append(rollback_msg)
            result["final_status"] = "rolled_back"
            return False, result

        result["messages"].append("Tests passed")
        result["final_status"] = "deployed"

        # Update run state to DEPLOYED
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if run and run.state == RunState.TESTING:
            run.state = RunState.DEPLOYED
            self.db.commit()

            dispatch_webhook(EVENT_STATE_CHANGE, {
                "run_id": run_id,
                "from_state": "testing",
                "to_state": "deployed",
                "deployment_id": deployment.id
            })

        return True, result
