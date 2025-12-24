"""URL configuration for Workflow Hub app."""
from django.urls import path
from app.views import api, ui

urlpatterns = [
    # UI
    path('ui/', ui.dashboard, name='dashboard'),
    path('ui/project/<int:project_id>/', ui.project_view, name='project_view'),
    path('ui/run/<int:run_id>/', ui.run_view, name='run_view'),

    # API
    path('api/status', api.api_status, name='api_status'),

    # Projects
    path('api/projects', api.projects_list, name='projects_list'),
    path('api/projects/create', api.project_create, name='project_create'),
    path('api/projects/<int:project_id>', api.project_detail, name='project_detail'),

    # Requirements
    path('api/projects/<int:project_id>/requirements', api.requirements_list, name='requirements_list'),
    path('api/projects/<int:project_id>/requirements/create', api.requirement_create, name='requirement_create'),

    # Tasks
    path('api/projects/<int:project_id>/tasks', api.tasks_list, name='tasks_list'),
    path('api/projects/<int:project_id>/tasks/create', api.task_create, name='task_create'),
    path('api/tasks/<int:task_id>/status', api.task_update_status, name='task_update_status'),

    # Runs
    path('api/projects/<int:project_id>/runs', api.runs_list, name='runs_list'),
    path('api/projects/<int:project_id>/runs/create', api.run_create, name='run_create'),
    path('api/runs/<int:run_id>', api.run_detail, name='run_detail'),
    path('api/runs/<int:run_id>/report', api.run_submit_report, name='run_submit_report'),
    path('api/runs/<int:run_id>/advance', api.run_advance, name='run_advance'),
    path('api/runs/<int:run_id>/retry', api.run_retry, name='run_retry'),
    path('api/runs/<int:run_id>/approve-deploy', api.run_approve_deploy, name='run_approve_deploy'),

    # Threat Intel
    path('api/threat-intel', api.threat_intel_list, name='threat_intel_list'),
    path('api/threat-intel/create', api.threat_intel_create, name='threat_intel_create'),

    # Audit
    path('api/audit', api.audit_log, name='audit_log'),
]
