import { Handle, Position, type NodeProps } from 'reactflow'
import type { SubtaskNodeData } from '@/lib/api/types'

export function SubtaskNode({ data, selected }: NodeProps<SubtaskNodeData>) {
  return (
    <div
      className={`px-4 py-3 rounded-lg border-2 min-w-[200px] shadow-sm bg-green-50 border-green-300 ${
        selected ? 'ring-2 ring-blue-500 ring-offset-2' : ''
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="w-3 h-3 !bg-green-500"
      />

      <div className="flex items-center gap-2 mb-2">
        <span className="text-xl">🧩</span>
        <div className="flex-1">
          <div className="font-semibold text-sm text-gray-800">
            {data.label || 'Subtask Template'}
          </div>
          <div className="text-xs text-gray-500">
            {data.triggerFrom.toUpperCase()} → {data.triggerTo.toUpperCase()}
          </div>
        </div>
      </div>

      <div className="text-xs text-gray-600">
        Template:{' '}
        <span className={data.useCustomTemplate ? 'font-semibold' : 'font-mono'}>
          {data.useCustomTemplate ? 'Custom list' : data.templatePath}
        </span>
      </div>
      <div className="text-xs text-gray-600 mt-1">
        Auto stage: {data.autoAssignStage.toUpperCase()}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="w-3 h-3 !bg-green-500"
      />
    </div>
  )
}
