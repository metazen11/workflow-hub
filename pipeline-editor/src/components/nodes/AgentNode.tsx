'use client'

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import type { AgentNodeData } from '@/lib/api/types'

const agentIcons: Record<string, string> = {
  director: '🎯',
  pm: '📋',
  dev: '💻',
  qa: '🧪',
  security: '🔒',
  docs: '📝',
  cicd: '🚀',
}

const agentColors: Record<string, string> = {
  director: 'border-indigo-400 bg-indigo-50',
  pm: 'border-purple-400 bg-purple-50',
  dev: 'border-blue-400 bg-blue-50',
  qa: 'border-green-400 bg-green-50',
  security: 'border-red-400 bg-red-50',
  docs: 'border-yellow-400 bg-yellow-50',
  cicd: 'border-cyan-400 bg-cyan-50',
}

const priorityLabels: Record<number, string> = {
  1: 'Critical',
  2: 'High',
  3: 'Normal',
  4: 'Low',
}

export const AgentNode = memo(({ data, selected }: NodeProps<AgentNodeData>) => {
  const statusClasses = {
    idle: '',
    running: 'animate-pulse ring-2 ring-green-500',
    error: 'ring-2 ring-red-500',
  }

  const baseColor = agentColors[data.roleId] || 'border-gray-400 bg-gray-50'
  const statusClass = data.status ? statusClasses[data.status] : ''

  return (
    <div
      className={`
        px-4 py-3 rounded-lg border-2 shadow-md min-w-[130px]
        ${baseColor}
        ${statusClass}
        ${selected ? 'ring-2 ring-blue-600 ring-offset-2' : ''}
      `}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="w-3 h-3 bg-gray-400 border-2 border-white"
      />

      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">{agentIcons[data.roleId] || '🤖'}</span>
        <span className="font-semibold text-gray-900 text-sm">{data.label}</span>
      </div>

      <div className="flex flex-wrap gap-1 mb-2">
        <span className="px-1.5 py-0.5 bg-white/60 text-gray-600 rounded text-[10px]">
          {priorityLabels[data.priority] || 'Normal'}
        </span>
        <span className="px-1.5 py-0.5 bg-white/60 text-gray-600 rounded text-[10px]">
          {data.timeout}s timeout
        </span>
        {data.concurrency > 1 && (
          <span className="px-1.5 py-0.5 bg-white/60 text-gray-600 rounded text-[10px]">
            ×{data.concurrency}
          </span>
        )}
      </div>

      {data.status === 'running' && (
        <div className="flex items-center gap-1 text-xs text-green-700">
          <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
          Running
          {data.currentTaskId && <span className="text-gray-500">#{data.currentTaskId}</span>}
        </div>
      )}

      {data.promptOverride && (
        <div className="mt-1 text-[10px] text-gray-500 truncate">
          Custom prompt
        </div>
      )}

      <Handle
        type="source"
        position={Position.Right}
        className="w-3 h-3 bg-gray-400 border-2 border-white"
      />
    </div>
  )
})

AgentNode.displayName = 'AgentNode'
