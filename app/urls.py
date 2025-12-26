"""URL configuration for Workflow Hub app."""
from django.urls import path
from app.views import api, ui

urlpatterns = [
    # UI
    path('ui/', ui.dashboard, name='dashboard'),
    path('ui/projects/', ui.projects_list, name='projects_list'),
    path('ui/project/<int:project_id>/', ui.project_view, name='project_view'),
    path('ui/run/<int:run_id>/', ui.run_view, name='run_view'),
    path('ui/task/<int:task_id>/', ui.task_view, name='task_view'),
    path('ui/bugs/', ui.bugs_list, name='bugs_list'),
    path('ui/bugs/<int:bug_id>/', ui.bug_detail_view, name='bug_detail_view'),

    # API
    path('api/status', api.api_status, name='api_status'),

    # Projects
    path('api/projects', api.projects_list, name='projects_list'),
    path('api/projects/create', api.project_create, name='project_create'),
    path('api/projects/<int:project_id>', api.project_detail, name='project_detail'),
    path('api/projects/<int:project_id>/update', api.project_update, name='project_update'),
    path('api/projects/<int:project_id>/execute', api.project_execute, name='project_execute'),
    path('api/projects/<int:project_id>/refresh', api.project_refresh, name='project_refresh'),
    path('api/projects/<int:project_id>/context', api.orchestrator_context, name='orchestrator_context'),

    # Credentials
    path('api/projects/<int:project_id>/credentials', api.credentials_list, name='credentials_list'),
    path('api/projects/<int:project_id>/credentials/create', api.credential_create, name='credential_create'),
    path('api/credentials/<int:credential_id>', api.credential_detail, name='credential_detail'),
    path('api/credentials/<int:credential_id>/update', api.credential_update, name='credential_update'),
    path('api/credentials/<int:credential_id>/delete', api.credential_delete, name='credential_delete'),

    # Environments
    path('api/projects/<int:project_id>/environments', api.environments_list, name='environments_list'),
    path('api/projects/<int:project_id>/environments/create', api.environment_create, name='environment_create'),
    path('api/environments/<int:environment_id>', api.environment_detail, name='environment_detail'),
    path('api/environments/<int:environment_id>/update', api.environment_update, name='environment_update'),
    path('api/environments/<int:environment_id>/delete', api.environment_delete, name='environment_delete'),

    # Requirements
    path('api/projects/<int:project_id>/requirements', api.requirements_list, name='requirements_list'),
    path('api/projects/<int:project_id>/requirements/create', api.requirement_create, name='requirement_create'),

    # Tasks
    path('api/projects/<int:project_id>/tasks', api.tasks_list, name='tasks_list'),
    path('api/projects/<int:project_id>/tasks/create', api.task_create, name='task_create'),
    path('api/tasks/<int:task_id>/status', api.task_update_status, name='task_update_status'),
    path('api/tasks/<int:task_id>/execute', api.task_execute, name='task_execute'),
    path('api/tasks/<int:task_id>/context', api.task_context, name='task_context'),
    path('api/tasks/<int:task_id>/attachments', api.task_attachments_list, name='task_attachments_list'),
    path('api/tasks/<int:task_id>/attachments/upload', api.task_attachment_upload, name='task_attachment_upload'),
    path('api/tasks/<int:task_id>/attachments/<int:attachment_id>/download', api.task_attachment_download, name='task_attachment_download'),

    # Runs
    path('api/projects/<int:project_id>/runs', api.runs_list, name='runs_list'),
    path('api/projects/<int:project_id>/runs/create', api.run_create, name='run_create'),
    path('api/runs/<int:run_id>', api.run_detail, name='run_detail'),
    path('api/runs/<int:run_id>/report', api.run_submit_report, name='run_submit_report'),
    path('api/runs/<int:run_id>/advance', api.run_advance, name='run_advance'),
    path('api/runs/<int:run_id>/set-state', api.run_set_state, name='run_set_state'),
    path('api/runs/<int:run_id>/retry', api.run_retry, name='run_retry'),
    path('api/runs/<int:run_id>/reset-to-dev', api.run_reset_to_dev, name='run_reset_to_dev'),
    path('api/runs/<int:run_id>/create-tasks-from-findings', api.run_create_tasks_from_findings, name='run_create_tasks_from_findings'),
    path('api/runs/<int:run_id>/approve-deploy', api.run_approve_deploy, name='run_approve_deploy'),

    # Threat Intel
    path('api/threat-intel', api.threat_intel_list, name='threat_intel_list'),
    path('api/threat-intel/create', api.threat_intel_create, name='threat_intel_create'),

    # Audit
    path('api/audit', api.audit_log, name='audit_log'),
    path('api/projects/<int:project_id>/audit', api.project_audit_log, name='project_audit_log'),

    # Activity Feed (combined bugs, runs, events)
    path('api/activity', api.activity_feed, name='activity_feed'),

    # Webhooks (n8n integration)
    path('api/webhooks', api.webhooks_list, name='webhooks_list'),
    path('api/webhooks/create', api.webhook_create, name='webhook_create'),
    path('api/webhooks/<int:webhook_id>', api.webhook_detail, name='webhook_detail'),
    path('api/webhooks/<int:webhook_id>/update', api.webhook_update, name='webhook_update'),
    path('api/webhooks/<int:webhook_id>/delete', api.webhook_delete, name='webhook_delete'),

    # Bug Reports
    path('api/bugs', api.bug_list, name='bug_list'),
    path('api/bugs/create', api.bug_create, name='bug_create'),
    path('api/bugs/<int:bug_id>', api.bug_detail, name='bug_detail'),
    path('api/bugs/<int:bug_id>/status', api.bug_update_status, name='bug_update_status'),
    path('api/bugs/<int:bug_id>/kill', api.bug_kill, name='bug_kill'),

    # Kill endpoints (soft delete)
    path('api/runs/<int:run_id>/kill', api.run_kill, name='run_kill'),
]
