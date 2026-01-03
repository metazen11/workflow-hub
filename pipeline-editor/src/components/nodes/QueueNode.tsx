'use client'

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import type { QueueNodeData } from '@/lib/api/types'

export const QueueNode = memo(({ data, selected }: NodeProps<QueueNodeData>) => {
  const depth = data.depth ?? 0
  const isOverloaded = depth > data.maxDepth

  return (
    <div
      className={`
        px-4 py-3 rounded-lg border-2 shadow-md min-w-[120px]
        ${isOverloaded ? 'border-orange-500 bg-orange-50' : 'border-orange-300 bg-orange-50'}
        ${selected ? 'ring-2 ring-blue-600 ring-offset-2' : ''}
      `}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="w-3 h-3 bg-gray-400 border-2 border-white"
      />

      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">📥</span>
        <span className="font-semibold text-gray-900 text-sm">{data.label}</span>
      </div>

      {/* Queue depth visualization */}
      <div className="mb-2">
        <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
          <span>Depth</span>
          <span className={isOverloaded ? 'text-orange-600 font-bold' : ''}>
            {depth}/{data.maxDepth}
          </span>
        </div>
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all ${
              isOverloaded ? 'bg-orange-500' : 'bg-green-500'
            }`}
            style={{ width: `${Math.min((depth / data.maxDepth) * 100, 100)}%` }}
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {data.jobTypes.map((type) => (
          <span
            key={type}
            className="px-1.5 py-0.5 bg-white/60 text-gray-600 rounded text-[10px]"
          >
            {type.replace('_', ' ')}
          </span>
        ))}
      </div>

      {data.avgWaitTime !== undefined && data.avgWaitTime > 0 && (
        <div className="mt-2 text-xs text-gray-500">
          Avg wait: {Math.round(data.avgWaitTime)}s
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

QueueNode.displayName = 'QueueNode'
