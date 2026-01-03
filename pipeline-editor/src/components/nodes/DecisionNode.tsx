'use client'

import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import type { DecisionNodeData } from '@/lib/api/types'

export const DecisionNode = memo(({ data, selected }: NodeProps<DecisionNodeData>) => {
  const conditionLabels: Record<string, string> = {
    report_status: 'Report Status',
    manual_approval: 'Manual Approval',
    custom: 'Custom',
  }

  return (
    <div
      className={`
        relative px-4 py-3 min-w-[100px]
        ${selected ? 'ring-2 ring-blue-600 ring-offset-2' : ''}
      `}
    >
      {/* Diamond shape background */}
      <div
        className="absolute inset-0 border-2 border-purple-400 bg-purple-50 shadow-md"
        style={{
          transform: data.shape === 'diamond' ? 'rotate(45deg)' : 'none',
          borderRadius: data.shape === 'hexagon' ? '8px' : '4px',
        }}
      />

      {/* Content */}
      <div className="relative z-10 text-center">
        <Handle
          type="target"
          position={Position.Left}
          className="w-3 h-3 bg-gray-400 border-2 border-white"
        />

        <div className="text-lg mb-1">❓</div>
        <div className="font-semibold text-gray-900 text-sm mb-1">{data.label}</div>
        <div className="text-[10px] text-purple-600">
          {conditionLabels[data.condition.type] || data.condition.type}
        </div>

        {/* Pass output handle (right-top) */}
        <Handle
          type="source"
          position={Position.Right}
          id="pass"
          className="w-3 h-3 bg-green-500 border-2 border-white"
          style={{ top: '30%' }}
        />

        {/* Fail output handle (right-bottom) */}
        <Handle
          type="source"
          position={Position.Right}
          id="fail"
          className="w-3 h-3 bg-red-500 border-2 border-white"
          style={{ top: '70%' }}
        />
      </div>

      {/* Pass/Fail labels */}
      <div className="absolute right-[-30px] top-[25%] text-[10px] text-green-600 font-medium">
        Pass
      </div>
      <div className="absolute right-[-24px] top-[65%] text-[10px] text-red-600 font-medium">
        Fail
      </div>
    </div>
  )
})

DecisionNode.displayName = 'DecisionNode'
