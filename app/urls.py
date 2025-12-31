"""URL configuration for Workflow Hub app."""
from django.urls import path
from app.views import api, ui

urlpatterns = [
    # UI
    path('ui/', ui.dashboard, name='dashboard'),
    path('ui/projects/', ui.projects_list, name='projects_list'),
    path('ui/projects/<int:project_id>/board', ui.task_board_view, name='task_board_view'),
    path('ui/project/<int:project_id>/', ui.project_view, name='project_view'),
    path('ui/runs/', ui.runs_list, name='runs_list'),
    path('ui/run/<int:run_id>/', ui.run_view, name='run_view'),
    path('ui/task/<int:task_id>/', ui.task_view, name='task_view'),
    path('ui/tasks/', ui.tasks_list, name='tasks_list'),
    path('ui/bugs/', ui.bugs_list, name='bugs_list'),
    path('ui/bugs/<int:bug_id>/', ui.bug_detail_view, name='bug_detail_view'),

    # API
    path('api/status', api.api_status, name='api_status'),

    # Projects
    path('api/projects', api.projects_list, name='projects_list'),
    path('api/projects/create', api.project_create, name='project_create'),
    path('api/projects/discover', api.project_discover, name='project_discover'),
    path('api/projects/<int:project_id>', api.project_detail, name='project_detail'),
    path('api/projects/<int:project_id>/update', api.project_update, name='project_update'),
    path('api/projects/<int:project_id>/delete', api.project_delete, name='project_delete'),
    path('api/projects/<int:project_id>/execute', api.project_execute, name='project_execute'),
    path('api/projects/<int:project_id>/refresh', api.project_refresh, name='project_refresh'),
    path('api/projects/<int:project_id>/context', api.orchestrator_context, name='orchestrator_context'),
    path('api/projects/<int:project_id>/handoff/history', api.project_handoff_history, name='project_handoff_history'),

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
    path('api/tasks/<int:task_id>/update', api.task_update, name='task_update'),
    path('api/tasks/<int:task_id>/delete', api.task_delete, name='task_delete'),
    path('api/tasks/<int:task_id>/execute', api.task_execute, name='task_execute'),
    path('api/tasks/<int:task_id>/context', api.task_context, name='task_context'),
    path('api/tasks/<int:task_id>/details', api.task_details, name='task_details'),
    path('api/tasks/<int:task_id>/attachments', api.task_attachments_list, name='task_attachments_list'),
    path('api/tasks/<int:task_id>/attachments/upload', api.task_attachment_upload, name='task_attachment_upload'),
    path('api/tasks/<int:task_id>/attachments/<int:attachment_id>/download', api.task_attachment_download, name='task_attachment_download'),

    # Task Pipeline (individual task workflow)
    path('api/tasks/queue', api.task_queue, name='task_queue'),
    path('api/tasks/<int:task_id>/advance-stage', api.task_advance_stage, name='task_advance_stage'),
    path('api/tasks/<int:task_id>/set-stage', api.task_set_stage, name='task_set_stage'),
    path('api/tasks/<int:task_id>/start', api.task_start, name='task_start'),
    path('api/tasks/<int:task_id>/advance', api.task_advance, name='task_advance'),
    path('api/tasks/<int:task_id>/loop-back', api.task_loop_back, name='task_loop_back'),
    path('api/tasks/<int:task_id>/director/prepare', api.task_director_prepare, name='task_director_prepare'),

    # Task Handoffs (agent work cycle tracking)
    path('api/tasks/<int:task_id>/handoff', api.task_handoff_current, name='task_handoff_current'),
    path('api/tasks/<int:task_id>/handoff/create', api.task_handoff_create, name='task_handoff_create'),
    path('api/tasks/<int:task_id>/handoff/accept', api.task_handoff_accept, name='task_handoff_accept'),
    path('api/tasks/<int:task_id>/handoff/complete', api.task_handoff_complete, name='task_handoff_complete'),
    path('api/tasks/<int:task_id>/handoff/fail', api.task_handoff_fail, name='task_handoff_fail'),
    path('api/tasks/<int:task_id>/handoff/history', api.task_handoff_history, name='task_handoff_history'),

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
    path('api/runs/<int:run_id>/trigger-agent', api.run_trigger_agent, name='run_trigger_agent'),
    path('api/runs/<int:run_id>/trigger-pipeline', api.run_trigger_pipeline, name='run_trigger_pipeline'),
    path('api/runs/<int:run_id>/task-progress', api.run_task_progress, name='run_task_progress'),
    path('api/runs/<int:run_id>/kill', api.run_kill, name='run_kill'),
    path('api/runs/<int:run_id>/deploy', api.run_deploy, name='run_deploy'),
    path('api/runs/<int:run_id>/rollback', api.run_rollback, name='run_rollback'),
    path('api/runs/<int:run_id>/deployments', api.run_deployments, name='run_deployments'),
    path('api/runs/<int:run_id>/director/process', api.run_director_process, name='run_director_process'),

    # Threat Intel
    path('api/threat-intel', api.threat_intel_list, name='threat_intel_list'),
    path('api/threat-intel/create', api.threat_intel_create, name='threat_intel_create'),

    # Director Control Panel
    path('api/director/status', api.director_status, name='director_status'),
    path('api/director/start', api.director_start, name='director_start'),
    path('api/director/stop', api.director_stop, name='director_stop'),
    path('api/director/settings', api.director_settings_update, name='director_settings'),
    path('api/director/activity', api.director_activity, name='director_activity'),
    path('api/director/run-cycle', api.director_run_cycle, name='director_run_cycle'),

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

    # Proof History (database-backed, for agent memory)
    # Must come BEFORE generic proof patterns to avoid <path:filename> matching
    path('api/tasks/<int:task_id>/proof-history', api.task_proof_history, name='task_proof_history'),
    path('api/projects/<int:project_id>/proof-history', api.project_proof_history, name='project_proof_history'),
    path('api/tasks/<int:task_id>/proofs/<int:proof_id>/download', api.proof_download, name='proof_download'),

    # Proof-of-Work (evidence artifacts - filesystem based)
    path('api/<str:entity_type>/<int:entity_id>/proofs', api.proof_list, name='proof_list'),
    path('api/<str:entity_type>/<int:entity_id>/proofs/summary', api.proof_summary, name='proof_summary'),
    path('api/<str:entity_type>/<int:entity_id>/proofs/upload', api.proof_upload, name='proof_upload'),
    path('api/<str:entity_type>/<int:entity_id>/proofs/clear', api.proof_clear, name='proof_clear'),
    path('api/<str:entity_type>/<int:entity_id>/proofs/<path:filename>', api.proof_view, name='proof_view'),

    # LLM Service (Docker Model Runner - lightweight completions without Goose)
    path('api/llm/models', api.llm_models, name='llm_models'),
    path('api/llm/complete', api.llm_complete, name='llm_complete'),
    path('api/llm/chat', api.llm_chat, name='llm_chat'),
    path('api/llm/query', api.llm_query, name='llm_query'),
    path('api/llm/enrich-docs', api.llm_enrich_docs, name='llm_enrich_docs'),
    path('api/llm/review-code', api.llm_review_code, name='llm_review_code'),
    path('api/llm/requirements', api.llm_requirements, name='llm_requirements'),
    path('api/llm/summarize', api.llm_summarize, name='llm_summarize'),
    path('api/llm/extract-json', api.llm_extract_json, name='llm_extract_json'),

    # LLM Sessions (conversation persistence)
    path('api/llm/sessions', api.llm_sessions_list, name='llm_sessions_list'),
    path('api/llm/sessions/<int:session_id>', api.llm_session_detail, name='llm_session_detail'),
    path('api/llm/sessions/<int:session_id>/clear', api.llm_session_clear, name='llm_session_clear'),
    path('api/llm/sessions/<int:session_id>/export', api.llm_session_export, name='llm_session_export'),
    path('api/llm/sessions/name/<str:name>', api.llm_session_by_name, name='llm_session_by_name'),

    # Agent Prompt Builder (structured context for task execution)
    path('api/tasks/<int:task_id>/agent-prompt', api.build_agent_prompt_view, name='build_agent_prompt'),

    # Project Enrichment (LLM-powered documentation generation)
    path('api/projects/<int:project_id>/enrich', api.project_enrich, name='project_enrich'),
]
