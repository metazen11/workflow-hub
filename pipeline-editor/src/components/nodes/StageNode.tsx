'use client'

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import type { StageNodeData } from '@/lib/api/types'

const stageIcons: Record<string, string> = {
  pm: '📋',
  dev: '💻',
  qa: '🧪',
  sec: '🔒',
  docs: '📝',
  complete: '✅',
}

const stageColors: Record<string, string> = {
  pm: 'border-purple-300 bg-purple-50',
  dev: 'border-blue-300 bg-blue-50',
  qa: 'border-green-300 bg-green-50',
  sec: 'border-red-300 bg-red-50',
  docs: 'border-yellow-300 bg-yellow-50',
  complete: 'border-gray-300 bg-gray-50',
}

export const StageNode = memo(({ data, selected }: NodeProps<StageNodeData>) => {
  const statusClasses = {
    idle: '',
    processing: 'animate-pulse ring-2 ring-blue-500',
    waiting: 'ring-2 ring-yellow-400',
    error: 'ring-2 ring-red-500',
  }

  const baseColor = stageColors[data.stageId] || 'border-gray-300 bg-gray-50'
  const statusClass = data.status ? statusClasses[data.status] : ''

  return (
    <div
      className={`
        px-4 py-3 rounded-lg border-2 shadow-md min-w-[140px]
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
        <span className="text-lg">{stageIcons[data.stageId] || '📦'}</span>
        <span className="font-semibold text-gray-900 text-sm">{data.label}</span>
      </div>

      {data.description && (
        <div className="text-xs text-gray-500 mb-2">{data.description}</div>
      )}

      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-500">
          {data.taskCount ?? 0} task{(data.taskCount ?? 0) !== 1 ? 's' : ''}
        </span>
        {data.requiresApproval && (
          <span className="px-1.5 py-0.5 bg-orange-100 text-orange-700 rounded text-[10px]">
            Approval
          </span>
        )}
      </div>

      {data.activeTaskId && (
        <div className="mt-1 text-xs text-blue-600 font-medium">
          Active: #{data.activeTaskId}
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

StageNode.displayName = 'StageNode'
