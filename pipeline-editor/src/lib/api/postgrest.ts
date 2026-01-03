/**
 * PostgREST API Client
 *
 * Connects to PostgREST on localhost:3000 (via Next.js rewrite to /postgrest)
 */

import type {
  PipelineConfig,
  RoleConfig,
  DirectorSettings,
  Project,
  Task,
  LLMJob,
} from './types'

const POSTGREST_BASE = '/postgrest'

// Generic fetch wrapper
async function fetchPostgREST<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${POSTGREST_BASE}${endpoint}`
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Prefer': options.method === 'POST' ? 'return=representation' : 'return=minimal',
      ...options.headers,
    },
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`PostgREST error: ${response.status} - ${error}`)
  }

  // For DELETE/PATCH with return=minimal
  if (response.status === 204) {
    return {} as T
  }

  return response.json()
}

// Pipeline Configs
export const pipelineConfigs = {
  list: (projectId?: number) => {
    const filter = projectId ? `?project_id=eq.${projectId}&` : '?'
    return fetchPostgREST<PipelineConfig[]>(`/pipeline_configs${filter}order=created_at.desc`)
  },

  get: (id: number) => {
    return fetchPostgREST<PipelineConfig[]>(`/pipeline_configs?id=eq.${id}`)
      .then(results => results[0] || null)
  },

  getActive: (projectId: number) => {
    return fetchPostgREST<PipelineConfig[]>(
      `/pipeline_configs?project_id=eq.${projectId}&is_active=eq.true`
    ).then(results => results[0] || null)
  },

  create: (config: Partial<PipelineConfig>) => {
    return fetchPostgREST<PipelineConfig[]>('/pipeline_configs', {
      method: 'POST',
      body: JSON.stringify(config),
    }).then(results => results[0])
  },

  update: (id: number, updates: Partial<PipelineConfig>) => {
    return fetchPostgREST<void>(`/pipeline_configs?id=eq.${id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        ...updates,
        updated_at: new Date().toISOString(),
      }),
    })
  },

  delete: (id: number) => {
    return fetchPostgREST<void>(`/pipeline_configs?id=eq.${id}`, {
      method: 'DELETE',
    })
  },
}

// Role Configs (Agent Prompts)
export const roleConfigs = {
  list: () => {
    return fetchPostgREST<RoleConfig[]>('/role_configs?order=role.asc')
  },

  get: (role: string) => {
    return fetchPostgREST<RoleConfig[]>(`/role_configs?role=eq.${role}`)
      .then(results => results[0] || null)
  },

  update: (role: string, updates: Partial<RoleConfig>) => {
    return fetchPostgREST<void>(`/role_configs?role=eq.${role}`, {
      method: 'PATCH',
      body: JSON.stringify({
        ...updates,
        updated_at: new Date().toISOString(),
      }),
    })
  },
}

// Director Settings
export const directorSettings = {
  get: () => {
    return fetchPostgREST<DirectorSettings[]>('/director_settings?id=eq.1')
      .then(results => results[0] || null)
  },

  update: (updates: Partial<DirectorSettings>) => {
    return fetchPostgREST<void>('/director_settings?id=eq.1', {
      method: 'PATCH',
      body: JSON.stringify({
        ...updates,
        updated_at: new Date().toISOString(),
      }),
    })
  },
}

// Projects
export const projects = {
  list: () => {
    return fetchPostgREST<Project[]>('/projects?is_active=eq.true&order=name.asc')
  },

  get: (id: number) => {
    return fetchPostgREST<Project[]>(`/projects?id=eq.${id}`)
      .then(results => results[0] || null)
  },
}

// Tasks (for monitoring)
export const tasks = {
  listByProject: (projectId: number) => {
    return fetchPostgREST<Task[]>(
      `/tasks?project_id=eq.${projectId}&order=priority.desc,created_at.desc`
    )
  },

  listByStage: (stage: string) => {
    return fetchPostgREST<Task[]>(
      `/tasks?pipeline_stage=eq.${stage}&order=priority.desc`
    )
  },

  getInProgress: () => {
    return fetchPostgREST<Task[]>(
      `/tasks?status=eq.in_progress&order=priority.desc`
    )
  },

  // Get all active tasks (not DONE) with full details
  listActive: () => {
    return fetchPostgREST<Task[]>(
      `/tasks?status=neq.done&order=pipeline_stage.asc,priority.desc`
    )
  },

  // Get task counts by stage
  getAll: () => {
    return fetchPostgREST<Task[]>(
      `/tasks?select=id,title,status,pipeline_stage,priority,project_id&order=created_at.desc`
    )
  },

  autoAssignDev: () => {
    return fetchPostgREST<void>(
      `/tasks?or=(pipeline_stage.is.null,pipeline_stage.eq.NONE)`,
      {
        method: 'PATCH',
        body: JSON.stringify({
          pipeline_stage: 'DEV',
          updated_at: new Date().toISOString(),
        }),
      }
    )
  },
}

// Work Cycles (agent work sessions)
export interface WorkCycle {
  id: number
  task_id: number
  to_role: string
  status: string
  context?: string
  created_at: string
  completed_at?: string
}

export const workCycles = {
  listRecent: (limit = 20) => {
    return fetchPostgREST<WorkCycle[]>(
      `/work_cycles?order=created_at.desc&limit=${limit}`
    )
  },

  listPending: () => {
    return fetchPostgREST<WorkCycle[]>(
      `/work_cycles?status=eq.PENDING&order=created_at.asc`
    )
  },

  listByTask: (taskId: number) => {
    return fetchPostgREST<WorkCycle[]>(
      `/work_cycles?task_id=eq.${taskId}&order=created_at.desc`
    )
  },
}

// LLM Jobs (Queue)
export const llmJobs = {
  listPending: (limit = 20) => {
    return fetchPostgREST<LLMJob[]>(
      `/llm_jobs?status=eq.pending&order=priority.asc,created_at.asc&limit=${limit}`
    )
  },

  listRunning: () => {
    return fetchPostgREST<LLMJob[]>('/llm_jobs?status=eq.running')
  },

  getStats: () => {
    // This would ideally be a custom endpoint, but we can aggregate client-side
    return Promise.all([
      fetchPostgREST<LLMJob[]>('/llm_jobs?status=eq.pending'),
      fetchPostgREST<LLMJob[]>('/llm_jobs?status=eq.running'),
    ]).then(([pending, running]) => ({
      pendingCount: pending.length,
      runningCount: running.length,
      pending,
      running,
    }))
  },
}

export const workCycleActions = {
  delete: (id: number) => {
    return fetchPostgREST<void>(`/work_cycles?id=eq.${id}`, {
      method: 'DELETE',
    })
  },
}
