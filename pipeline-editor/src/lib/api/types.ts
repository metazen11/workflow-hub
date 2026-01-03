// Pipeline Stage
export type StageId = 'pm' | 'dev' | 'qa' | 'sec' | 'docs' | 'complete'

export type StageStatus = 'idle' | 'processing' | 'waiting' | 'error'

// Agent Role
export type AgentRoleId = 'director' | 'pm' | 'dev' | 'qa' | 'security' | 'docs' | 'cicd'

export type AgentStatus = 'idle' | 'running' | 'error'

// Job Queue
export type JobType = 'llm_complete' | 'llm_chat' | 'llm_query' | 'vision_analyze' | 'agent_run'

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timeout'

export type JobPriority = 1 | 2 | 3 | 4 // CRITICAL, HIGH, NORMAL, LOW

// Dynamic variable for prompt templates
export interface DynamicVariable {
  name: string
  description?: string
  defaultValue?: string
  required?: boolean
}

// Node Types
export interface StageNodeData {
  type: 'stage'
  stageId: StageId
  label: string
  description?: string
  autoAdvance: boolean
  requiresApproval: boolean
  timeout: number
  // Stage-specific prompt/config
  entryPrompt?: string // Prompt when task enters this stage
  exitPrompt?: string // Prompt when task exits this stage
  validationRules?: string[] // Rules to validate before advancing
  variables?: DynamicVariable[] // Custom variables for this stage
  // Live status
  taskCount?: number
  activeTaskId?: number
  status?: StageStatus
}

export interface SubtaskNodeData {
  type: 'subtask'
  label: string
  triggerFrom: StageId
  triggerTo: StageId
  templatePath: string
  templateItems?: QualityRequirement[]
  useCustomTemplate?: boolean
  autoAssignStage: StageId
  inheritRequirements: boolean
}

export interface QualityRequirement {
  id: string
  title: string
  subtask_title?: string
  description?: string
  acceptance_criteria?: string[]
}

export interface AgentNodeData {
  type: 'agent'
  roleId: AgentRoleId
  label: string
  // Prompt customization
  promptOverride?: string // Full prompt override
  promptPrefix?: string // Added before base prompt
  promptSuffix?: string // Added after base prompt
  systemContext?: string // Additional system context
  // Config
  checksEnabled?: string[]
  priority: JobPriority
  timeout: number
  concurrency: number
  maxRetries?: number
  retryDelay?: number
  // Dynamic variables
  variables?: DynamicVariable[]
  // Live status
  status?: AgentStatus
  currentTaskId?: number
  lastRunAt?: string
}

export interface QueueNodeData {
  type: 'queue'
  queueId: string
  label: string
  jobTypes: JobType[]
  maxDepth: number
  // Live status
  depth?: number
  oldestJobAge?: number
  avgWaitTime?: number
}

export interface DecisionNodeData {
  type: 'decision'
  decisionId: string
  label: string
  shape: 'diamond' | 'hexagon'
  condition: {
    type: 'report_status' | 'manual_approval' | 'custom' | 'script'
    passValue: string
    failValue: string
    // For custom/script conditions
    customScript?: string // Python/JS code to evaluate
    customPrompt?: string // LLM prompt to evaluate condition
  }
  passOutput: string
  failOutput: string
  // Prompt for manual approval
  approvalPrompt?: string
  approvalInstructions?: string
  // Dynamic variables
  variables?: DynamicVariable[]
}

// Code Snippet Node - runs custom Python/shell code
export interface CodeSnippetNodeData {
  type: 'code_snippet'
  snippetId: string
  label: string
  language: 'python' | 'bash' | 'javascript'
  code: string
  timeout: number
  runOn: 'task_enter' | 'task_exit' | 'manual' | 'schedule'
  schedule?: string // cron expression if runOn is 'schedule'
  inputVars?: string[] // variables passed to the script
  outputVar?: string // variable name for script output
  // Pass/fail behavior
  canFail?: boolean // If true, script can signal pass/fail
  failOn?: 'exit_code' | 'output' | 'exception' // What triggers failure
  failPattern?: string // Regex pattern for output-based failure detection
  onFailAction?: 'stop' | 'continue' | 'route' // What happens on failure
  failRouteTarget?: string // Node ID to route to on failure
  // Dynamic variables
  variables?: DynamicVariable[]
  // Live status
  lastRunAt?: string
  lastRunStatus?: 'success' | 'error' | 'timeout'
  lastRunOutput?: string
}

export type PipelineNodeData = StageNodeData | AgentNodeData | QueueNodeData | DecisionNodeData | CodeSnippetNodeData | SubtaskNodeData

// Pipeline Node (React Flow compatible)
export interface PipelineNode {
  id: string
  type: 'stage' | 'agent' | 'queue' | 'decision' | 'code_snippet' | 'subtask'
  position: { x: number; y: number }
  data: PipelineNodeData
}

// Pipeline Edge
export interface PipelineEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
  type?: 'default' | 'animated' | 'status'
  animated?: boolean
  style?: Record<string, string | number>
  data?: {
    label?: string
  }
}

// Canvas Config
export interface CanvasConfig {
  zoom: number
  panX: number
  panY: number
}

// Pipeline Settings
export interface PipelineSettings {
  pipeline?: {
    name: string
    description?: string
    autoStart: boolean
    maxConcurrentTasks: number
  }
  director?: {
    enabled: boolean
    pollInterval: number
    enforceTDD: boolean
    enforceDRY: boolean
    enforceSecurity: boolean
  }
  notifications?: {
    onStageComplete: boolean
    onFailure: boolean
    onApprovalRequired: boolean
  }
  timeouts?: Record<StageId, number>
}

// Pipeline Config (Database Model)
export interface PipelineConfig {
  id: number
  project_id: number
  name: string
  description?: string
  version: number
  is_active: boolean
  canvas_config: CanvasConfig
  nodes: PipelineNode[]
  edges: PipelineEdge[]
  settings: PipelineSettings
  created_by: string
  created_at: string
  updated_at?: string
}

// Live Status (from Flask API)
export interface LiveStatus {
  stage_counts: Record<string, number>
  queue_status: Array<{
    status: string
    type: string
    count: number
  }>
  active_work_cycles: Array<{
    id: number
    task_id: number
    stage: string
    to_role: string
    status: string
  }>
  director: {
    enabled: boolean
    poll_interval: number
    daemon_started_at?: string
    is_running: boolean
  }
  timestamp: string
}

// Role Config (from role_configs table)
export interface RoleConfig {
  id: number
  role: AgentRoleId
  name: string
  description?: string
  prompt: string
  checks?: Record<string, boolean>
  requires_approval: boolean
  active: boolean
  created_at: string
  updated_at?: string
}

// Director Settings (from director_settings table)
export interface DirectorSettings {
  id: number
  enabled: boolean
  poll_interval: number
  enforce_tdd: boolean
  enforce_dry: boolean
  enforce_security: boolean
  include_images: boolean
  vision_model: string
  daemon_started_at?: string
  updated_at?: string
}

// Project (for project selection)
export interface Project {
  id: number
  name: string
  description?: string
  is_active: boolean
}

// Task (for monitoring)
export interface Task {
  id: number
  project_id: number
  task_id: string
  title: string
  status: string
  pipeline_stage: StageId | null
  priority: number
}

// LLM Job (for queue monitoring)
export interface LLMJob {
  id: number
  job_type: JobType
  status: JobStatus
  priority: JobPriority
  project_id?: number
  task_id?: number
  created_at: string
  started_at?: string
  completed_at?: string
  timeout_seconds: number
  worker_id?: string
}
