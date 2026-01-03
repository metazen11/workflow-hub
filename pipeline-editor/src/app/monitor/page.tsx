'use client'

import { useState, useEffect, useCallback } from 'react'
import { tasks, llmJobs, workCycles as postgrestWorkCycles, directorSettings, projects } from '@/lib/api/postgrest'
import { queueStatus as queueStatusApi, workCycleActions } from '@/lib/api/django'
import type { Task, LLMJob, DirectorSettings, Project } from '@/lib/api/types'
import type { WorkCycle } from '@/lib/api/postgrest'

// Link to main Workflow Hub
const HUB_BASE_URL = 'http://localhost:8000'

// Pipeline stages in order
const STAGES = ['PM', 'DEV', 'QA', 'SEC', 'DOCS', 'COMPLETE'] as const

// Stage colors
const STAGE_COLORS: Record<string, string> = {
  PM: 'bg-blue-100 text-blue-800 border-blue-300',
  DEV: 'bg-green-100 text-green-800 border-green-300',
  QA: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  SEC: 'bg-red-100 text-red-800 border-red-300',
  DOCS: 'bg-purple-100 text-purple-800 border-purple-300',
  COMPLETE: 'bg-gray-100 text-gray-800 border-gray-300',
}

// Status colors for jobs
const JOB_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  timeout: 'bg-orange-100 text-orange-800',
  cancelled: 'bg-gray-100 text-gray-800',
}

// Extended work cycle with task info
interface WorkCycleWithTask extends WorkCycle {
  task?: Task
}

type QueueStatusResponse = Awaited<ReturnType<typeof queueStatusApi.get>>

export default function MonitorPage() {
  const [allTasks, setAllTasks] = useState<Task[]>([])
  const [recentJobs, setRecentJobs] = useState<LLMJob[]>([])
  const [pendingCycles, setPendingCycles] = useState<WorkCycleWithTask[]>([])
  const [recentCycles, setRecentCycles] = useState<WorkCycleWithTask[]>([])
  const [director, setDirector] = useState<DirectorSettings | null>(null)
  const [projectList, setProjectList] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedStage, setSelectedStage] = useState<string | null>(null)
  const [showStaleWarning, setShowStaleWarning] = useState(false)
  const [queueStatus, setQueueStatus] = useState<QueueStatusResponse | null>(null)
  const [queueError, setQueueError] = useState<string | null>(null)

  // Fetch all monitoring data
  const fetchData = useCallback(async () => {
    try {
      const [tasksData, jobsData, pendingCyclesData, recentCyclesData, directorData, projectsData] = await Promise.all([
        tasks.getAll(),
        llmJobs.getStats(),
        postgrestWorkCycles.listPending(),
        postgrestWorkCycles.listRecent(20),
        directorSettings.get(),
        projects.list(),
      ])

      setAllTasks(tasksData)
      setRecentJobs([...jobsData.running, ...jobsData.pending])
      setDirector(directorData)
      setProjectList(projectsData)

      // Create a task lookup map
      const taskMap = new Map(tasksData.map(t => [t.id, t]))

      // Enrich work cycles with task info and detect stale cycles
      const enrichCycles = (cycles: WorkCycle[]): WorkCycleWithTask[] => {
        return cycles.map(cycle => ({
          ...cycle,
          task: taskMap.get(cycle.task_id),
        }))
      }

      const enrichedPending = enrichCycles(pendingCyclesData)
      const enrichedRecent = enrichCycles(recentCyclesData)

      setPendingCycles(enrichedPending)
      setRecentCycles(enrichedRecent)

      // Check for stale cycles (PENDING but task is done)
      const staleCycles = enrichedPending.filter(c => c.task?.status === 'done')
      setShowStaleWarning(staleCycles.length > 0)

      setLastRefresh(new Date())
    } catch (err) {
      console.error('Failed to fetch monitoring data:', err)
    } finally {
      setLoading(false)
    }

    // Queue status from Django (optional - returns null if Django is down)
    const status = await queueStatusApi.get()
    if (status) {
      setQueueStatus(status)
      setQueueError(null)
    } else {
      // Django not running - silently fall back to PostgREST data only
      setQueueStatus(null)
      setQueueError('Django offline')
    }
  }, [])

  // Initial load and auto-refresh
  useEffect(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(fetchData, 5000) // 5 second refresh
    return () => clearInterval(interval)
  }, [autoRefresh, fetchData])

  const handleDeleteWorkCycle = useCallback(async (cycleId: number) => {
    if (!confirm('Delete this work cycle from the queue?')) {
      return
    }
    try {
      await workCycleActions.delete(cycleId)
      await fetchData()
    } catch (err) {
      console.error('Failed to delete work cycle:', err)
    }
  }, [fetchData])

  // Group tasks by stage (comparing lowercase since pipeline_stage uses lowercase StageId)
  const tasksByStage = STAGES.reduce((acc, stage) => {
    acc[stage] = allTasks.filter(t => t.pipeline_stage?.toUpperCase() === stage)
    return acc
  }, {} as Record<string, Task[]>)

  const isUnstaged = (task: Task) => {
    if (!task.pipeline_stage) return true
    return task.pipeline_stage.toUpperCase() === 'NONE'
  }

  // Tasks with no stage (need attention)
  const unstaged = allTasks.filter(t => isUnstaged(t) && t.status !== 'done')

  // Active (non-done) task count
  const activeTasks = allTasks.filter(t => t.status !== 'done')

  // Get project name by id
  const getProjectName = (projectId: number | null | undefined) => {
    if (!projectId) return 'Unknown'
    const project = projectList.find(p => p.id === projectId)
    return project?.name || `Project ${projectId}`
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-56px)]">
        <div className="text-gray-500">Loading monitoring data...</div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Pipeline Monitor</h1>
          <p className="text-sm text-gray-500">
            Last updated: {lastRefresh.toLocaleTimeString()}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded"
            />
            Auto-refresh (5s)
          </label>
          <button
            onClick={fetchData}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
          >
            Refresh Now
          </button>
        </div>
      </div>

      {/* Director Status */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="font-semibold text-gray-900 mb-3">Director Status</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <span className="text-xs text-gray-500 uppercase">Status</span>
            <div className={`font-medium ${director?.enabled ? 'text-green-600' : 'text-red-600'}`}>
              {director?.enabled ? 'Enabled' : 'Disabled'}
            </div>
          </div>
          <div>
            <span className="text-xs text-gray-500 uppercase">Poll Interval</span>
            <div className="font-medium">{director?.poll_interval || 30}s</div>
          </div>
          <div>
            <span className="text-xs text-gray-500 uppercase">Started</span>
            <div className="font-medium text-sm">
              {director?.daemon_started_at
                ? new Date(director.daemon_started_at).toLocaleString()
                : 'Not running'}
            </div>
          </div>
          <div>
            <span className="text-xs text-gray-500 uppercase">Enforcement</span>
            <div className="flex gap-2 text-xs">
              {director?.enforce_tdd && <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded">TDD</span>}
              {director?.enforce_dry && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded">DRY</span>}
              {director?.enforce_security && <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded">SEC</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline Overview */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="font-semibold text-gray-900 mb-3">Pipeline Overview</h2>
        <div className="flex items-center gap-2 overflow-x-auto pb-2">
          {STAGES.map((stage, idx) => {
            const count = tasksByStage[stage]?.length || 0
            const isSelected = selectedStage === stage
            return (
              <div key={stage} className="flex items-center">
                <button
                  onClick={() => setSelectedStage(isSelected ? null : stage)}
                  className={`flex flex-col items-center p-3 rounded-lg border-2 min-w-[100px] transition-all ${
                    STAGE_COLORS[stage]
                  } ${isSelected ? 'ring-2 ring-offset-2 ring-blue-500' : ''}`}
                >
                  <span className="text-2xl font-bold">{count}</span>
                  <span className="text-xs font-medium">{stage}</span>
                </button>
                {idx < STAGES.length - 1 && (
                  <div className="mx-1 text-gray-300 text-xl">→</div>
                )}
              </div>
            )
          })}
        </div>
        {unstaged.length > 0 && (
          <div className="mt-3 text-sm text-orange-600">
            {unstaged.length} task(s) have no pipeline stage assigned
          </div>
        )}
      </div>

      {/* Task Details by Stage */}
      {selectedStage && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-gray-900">
              Tasks in {selectedStage} ({tasksByStage[selectedStage]?.length || 0})
            </h2>
            <button
              onClick={() => setSelectedStage(null)}
              className="text-gray-400 hover:text-gray-600"
            >
              Close
            </button>
          </div>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {tasksByStage[selectedStage]?.length === 0 ? (
              <div className="text-gray-500 text-sm">No tasks in this stage</div>
            ) : (
              tasksByStage[selectedStage]?.map(task => (
                <div
                  key={task.id}
                  className="flex items-center justify-between p-2 bg-gray-50 rounded border"
                >
                  <div className="flex-1 min-w-0">
                    <a
                      href={`${HUB_BASE_URL}/ui/tasks/${task.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-sm text-blue-600 hover:text-blue-800 hover:underline truncate block"
                    >
                      {task.title}
                    </a>
                    <div className="text-xs text-gray-500">
                      ID: {task.id} | Project: {getProjectName(task.project_id)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-2">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      task.status === 'IN_PROGRESS' ? 'bg-blue-100 text-blue-700' :
                      task.status === 'done' ? 'bg-green-100 text-green-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {task.status}
                    </span>
                    <a
                      href={`${HUB_BASE_URL}/ui/tasks/${task.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-500 hover:underline"
                    >
                      View →
                    </a>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Two-column layout for queues */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Pending Work Cycles */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h2 className="font-semibold text-gray-900 mb-3">
            Pending Work Cycles ({pendingCycles.length})
            {showStaleWarning && (
              <span className="ml-2 text-xs text-orange-600 font-normal">
                (includes stale cycles)
              </span>
            )}
          </h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {pendingCycles.length === 0 ? (
              <div className="text-gray-500 text-sm">No pending work cycles</div>
            ) : (
              pendingCycles.map(cycle => {
                const isStale = cycle.task?.status === 'done'
                return (
                  <div
                    key={cycle.id}
                    className={`flex items-center justify-between gap-2 p-2 rounded border ${
                      isStale
                        ? 'bg-orange-50 border-orange-300'
                        : 'bg-yellow-50 border-yellow-200'
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <a
                        href={`${HUB_BASE_URL}/ui/tasks/${cycle.task_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-medium text-sm text-blue-600 hover:text-blue-800 hover:underline truncate block"
                      >
                        {cycle.task?.title || `Task #${cycle.task_id}`}
                      </a>
                      <div className="text-xs text-gray-500 flex items-center gap-2">
                        <span>Waiting for: {cycle.to_role.toUpperCase()}</span>
                        {isStale && (
                          <span className="text-orange-600 font-medium">
                            (Task already DONE - stale cycle)
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right ml-2">
                      <span className="text-xs text-gray-400 block">
                        {new Date(cycle.created_at).toLocaleDateString()}
                      </span>
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleDeleteWorkCycle(cycle.id)}
                          className="text-xs text-red-600 hover:underline"
                        >
                          Delete
                        </button>
                        <a
                          href={`${HUB_BASE_URL}/ui/tasks/${cycle.task_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-blue-500 hover:underline"
                        >
                          View →
                        </a>
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Job Queue */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h2 className="font-semibold text-gray-900 mb-3">
            Job Queue ({recentJobs.length})
          </h2>
          {queueError && (
            <div className="mb-2 text-xs text-red-600">{queueError}</div>
          )}
          {queueStatus && (
            <div className="mb-3 text-xs text-gray-600 border border-gray-100 rounded p-2 bg-gray-50">
              <div className="flex items-center justify-between">
                <span>Pending: {queueStatus.queue.pending.total}</span>
                <span>Running: {queueStatus.queue.running_count}</span>
                <span>Avg wait: {Math.round(queueStatus.queue.avg_wait_seconds)}s</span>
              </div>
              <div className="mt-1 flex items-center justify-between">
                <span>
                  Workers: {queueStatus.workers.started ? 'started' : 'stopped'}
                </span>
                <span>
                  Busy: {queueStatus.workers.workers.filter(w => w.is_busy).length}/
                  {queueStatus.workers.workers.length}
                </span>
              </div>
            </div>
          )}
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {recentJobs.length === 0 ? (
              <div className="text-gray-500 text-sm">No jobs in queue</div>
            ) : (
              recentJobs.map(job => (
                <div
                  key={job.id}
                  className="flex items-center justify-between p-2 bg-gray-50 rounded border"
                >
                  <div>
                    <div className="font-medium text-sm">{job.job_type}</div>
                    <div className="text-xs text-gray-500">
                      Job #{job.id} | Priority: {job.priority}
                    </div>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-xs ${JOB_STATUS_COLORS[job.status] || 'bg-gray-100'}`}>
                    {job.status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="font-semibold text-gray-900 mb-3">Recent Work Cycles</h2>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {recentCycles.map(cycle => (
            <div
              key={cycle.id}
              className="flex items-center justify-between p-2 bg-gray-50 rounded border"
            >
              <div className="flex-1 min-w-0">
                <a
                  href={`${HUB_BASE_URL}/ui/tasks/${cycle.task_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-sm text-blue-600 hover:text-blue-800 hover:underline truncate block"
                >
                  {cycle.task?.title || `Task #${cycle.task_id}`}
                </a>
                <div className="text-xs text-gray-500">
                  → {cycle.to_role.toUpperCase()} | {new Date(cycle.created_at).toLocaleString()}
                </div>
              </div>
              <span className={`px-2 py-0.5 rounded text-xs ml-2 ${
                cycle.status === 'COMPLETED' ? 'bg-green-100 text-green-700' :
                cycle.status === 'PENDING' ? 'bg-yellow-100 text-yellow-700' :
                cycle.status === 'IN_PROGRESS' ? 'bg-blue-100 text-blue-700' :
                'bg-gray-100 text-gray-700'
              }`}>
                {cycle.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Unstaged Tasks */}
      {unstaged.length > 0 && (
        <div className="bg-white rounded-lg border border-orange-200 p-4">
          <h2 className="font-semibold text-orange-700 mb-3">
            Unstaged Tasks ({unstaged.length})
          </h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {unstaged.map(task => (
              <div
                key={task.id}
                className="flex items-center justify-between gap-2 p-2 rounded border bg-orange-50 border-orange-200"
              >
                <div className="flex-1 min-w-0">
                  <a
                    href={`${HUB_BASE_URL}/ui/tasks/${task.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline truncate block"
                  >
                    {task.title}
                  </a>
                  <div className="text-xs text-gray-500">
                    Project: {getProjectName(task.project_id)} • Priority {task.priority}
                  </div>
                </div>
                <span className="text-xs text-orange-600">No stage assigned</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
          <div className="text-3xl font-bold text-blue-600">{activeTasks.length}</div>
          <div className="text-sm text-gray-500">Active Tasks</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
          <div className="text-3xl font-bold text-yellow-600">{pendingCycles.length}</div>
          <div className="text-sm text-gray-500">Pending Cycles</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
          <div className="text-3xl font-bold text-green-600">{tasksByStage['COMPLETE']?.length || 0}</div>
          <div className="text-sm text-gray-500">Completed</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
          <div className="text-3xl font-bold text-purple-600">{recentJobs.length}</div>
          <div className="text-sm text-gray-500">Jobs in Queue</div>
        </div>
      </div>
    </div>
  )
}
