/**
 * Django API Client
 *
 * Connects to Django backend on localhost:8000 (via Next.js rewrite to /api)
 *
 * USE THIS FOR:
 * - Actions that require business logic (director control, job management)
 * - Operations that need background processing
 * - Complex workflows that can't be done via simple CRUD
 *
 * USE PostgREST FOR:
 * - Simple CRUD reads (list, get)
 * - Simple CRUD writes (create, update, delete)
 * - Direct database access without business logic
 */

import type { LiveStatus } from './types'

const DJANGO_BASE = '/api'

interface FetchOptions extends RequestInit {
  silent?: boolean  // Don't throw on error, return null instead
}

// Generic fetch wrapper
async function fetchDjango<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const { silent, ...fetchOptions } = options
  const url = `${DJANGO_BASE}${endpoint}`

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
      },
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Django API error: ${response.status} - ${error}`)
    }

    return response.json()
  } catch (err) {
    if (silent) {
      return null as T
    }
    throw err
  }
}

// Live Status (aggregated for monitoring - requires computation)
export const liveStatus = {
  get: (projectId?: number) => {
    const params = projectId ? `?project_id=${projectId}` : ''
    return fetchDjango<LiveStatus>(`/pipeline/live-status${params}`)
  },
}

// YAML Operations (requires file generation logic)
export const yaml = {
  export: (configId: number) => {
    return fetchDjango<{ yaml: string; filename: string }>('/pipeline/export-yaml', {
      method: 'POST',
      body: JSON.stringify({ config_id: configId }),
    })
  },

  import: (yamlContent: string, projectId: number) => {
    return fetchDjango<{ id: number; success: boolean }>('/pipeline/import-yaml', {
      method: 'POST',
      body: JSON.stringify({
        yaml: yamlContent,
        project_id: projectId,
      }),
    })
  },
}

// Validation (requires business logic)
export const validation = {
  validate: (config: { nodes: unknown[]; edges: unknown[]; settings: unknown }) => {
    return fetchDjango<{ valid: boolean; errors: string[] }>('/pipeline/validate', {
      method: 'POST',
      body: JSON.stringify(config),
    })
  },
}

// Templates (could be PostgREST, but templates are generated)
export const templates = {
  list: () => {
    return fetchDjango<Array<{
      id: string
      name: string
      description: string
      nodes: unknown[]
      edges: unknown[]
      settings: unknown
    }>>('/pipeline/templates')
  },
}

// Queue Status (aggregated from multiple sources)
// Returns null if Django is offline (uses silent mode)
export const queueStatus = {
  get: () => {
    return fetchDjango<{
      queue: {
        pending: { llm: number; agent: number; vision: number; total: number }
        running: unknown[]
        running_count: number
        avg_wait_seconds: number
      }
      workers: {
        started: boolean
        workers: Array<{
          id: string
          job_types: string[]
          is_busy: boolean
          current_job: number | null
        }>
      }
      dmr: { healthy: boolean; error?: string }
      director: { running: boolean; enabled: boolean; poll_interval: number }
    } | null>('/queue/status', { silent: true })
  },
}

// Director Control (daemon management - requires server-side state)
export const director = {
  start: () => {
    return fetchDjango<{ success: boolean; message: string }>('/director/start', {
      method: 'POST',
    })
  },

  stop: () => {
    return fetchDjango<{ success: boolean; message: string }>('/director/stop', {
      method: 'POST',
    })
  },

  runCycle: () => {
    return fetchDjango<{ success: boolean; result: unknown }>('/director/run-cycle', {
      method: 'POST',
    })
  },
}

// Work Cycle Actions (business logic for cleanup)
export const workCycleActions = {
  delete: (id: number) => {
    return fetchDjango<{ success: boolean; work_cycle_id: number }>(`/work_cycles/${id}/delete`, {
      method: 'POST',
    })
  },
}
