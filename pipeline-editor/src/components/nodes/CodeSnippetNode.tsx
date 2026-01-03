import { Handle, Position, type NodeProps } from 'reactflow'
import type { CodeSnippetNodeData } from '@/lib/api/types'

// Language icons/labels
const LANGUAGE_CONFIG = {
  python: { icon: '🐍', label: 'Python', color: 'bg-yellow-100 border-yellow-400' },
  bash: { icon: '💻', label: 'Bash', color: 'bg-gray-100 border-gray-400' },
  javascript: { icon: '⚡', label: 'JavaScript', color: 'bg-yellow-50 border-yellow-300' },
}

// Run trigger labels
const RUN_ON_LABELS = {
  task_enter: 'On Task Enter',
  task_exit: 'On Task Exit',
  manual: 'Manual',
  schedule: 'Scheduled',
}

export function CodeSnippetNode({ data, selected }: NodeProps<CodeSnippetNodeData>) {
  const langConfig = LANGUAGE_CONFIG[data.language]
  const statusColor = data.lastRunStatus === 'success'
    ? 'text-green-600'
    : data.lastRunStatus === 'error'
    ? 'text-red-600'
    : data.lastRunStatus === 'timeout'
    ? 'text-orange-600'
    : 'text-gray-400'

  return (
    <div
      className={`px-4 py-3 rounded-lg border-2 min-w-[180px] shadow-sm ${langConfig.color} ${
        selected ? 'ring-2 ring-blue-500 ring-offset-2' : ''
      }`}
    >
      {/* Input handle */}
      <Handle
        type="target"
        position={Position.Left}
        className="w-3 h-3 !bg-gray-500"
      />

      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xl">{langConfig.icon}</span>
        <div className="flex-1">
          <div className="font-semibold text-sm text-gray-800">
            {data.label || 'Code Snippet'}
          </div>
          <div className="text-xs text-gray-500">
            {langConfig.label}
          </div>
        </div>
      </div>

      {/* Code preview */}
      <div className="bg-white bg-opacity-60 rounded p-2 mb-2 font-mono text-xs text-gray-600 max-h-16 overflow-hidden">
        {data.code ? (
          <pre className="whitespace-pre-wrap break-all">
            {data.code.slice(0, 100)}{data.code.length > 100 ? '...' : ''}
          </pre>
        ) : (
          <span className="text-gray-400 italic">No code defined</span>
        )}
      </div>

      {/* Run config & status */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-500">
          {RUN_ON_LABELS[data.runOn]}
        </span>
        {data.lastRunAt && (
          <span className={statusColor}>
            {data.lastRunStatus === 'success' ? '✓' : data.lastRunStatus === 'error' ? '✗' : '⏱'}
          </span>
        )}
      </div>

      {/* Schedule indicator */}
      {data.runOn === 'schedule' && data.schedule && (
        <div className="text-xs text-gray-400 mt-1">
          ⏰ {data.schedule}
        </div>
      )}

      {/* Output handle */}
      <Handle
        type="source"
        position={Position.Right}
        className="w-3 h-3 !bg-gray-500"
      />
    </div>
  )
}
