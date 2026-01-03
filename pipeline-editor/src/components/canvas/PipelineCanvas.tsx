'use client'

import { useCallback, useEffect, useMemo, useRef, DragEvent } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  Node,
  Edge,
  BackgroundVariant,
  Panel,
  ReactFlowProvider,
  useReactFlow,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { nodeTypes } from '@/components/nodes'
import type { PipelineNode, PipelineEdge, StageNodeData, AgentNodeData, QueueNodeData, DecisionNodeData, CodeSnippetNodeData, SubtaskNodeData } from '@/lib/api/types'

interface PipelineCanvasProps {
  nodes: PipelineNode[]
  edges: PipelineEdge[]
  onNodesChange?: (nodes: PipelineNode[]) => void
  onEdgesChange?: (edges: PipelineEdge[]) => void
  onNodeClick?: (node: PipelineNode) => void
  onNodeAdd?: (node: PipelineNode) => void
  readOnly?: boolean
}

// Helper to generate unique IDs
let nodeIdCounter = 0
const generateNodeId = (type: string) => `${type}-${Date.now()}-${++nodeIdCounter}`

// Create default data for each node type
const createNodeData = (nodeType: string, extra: Record<string, string> = {}): PipelineNode['data'] => {
  switch (nodeType) {
    case 'stage':
      return {
        type: 'stage',
        stageId: extra.stageId || 'dev',
        label: `${(extra.stageId || 'dev').toUpperCase()} Stage`,
        autoAdvance: true,
        requiresApproval: false,
        timeout: 3600,
        taskCount: 0,
        status: 'idle',
      } as StageNodeData
    case 'agent':
      return {
        type: 'agent',
        roleId: extra.roleId || 'dev',
        label: `${(extra.roleId || 'dev').toUpperCase()} Agent`,
        priority: 3,
        timeout: 600,
        concurrency: 1,
        status: 'idle',
      } as AgentNodeData
    case 'queue':
      return {
        type: 'queue',
        queueId: `queue-${Date.now()}`,
        label: 'Job Queue',
        jobTypes: ['agent_run'],
        maxDepth: 10,
        depth: 0,
        avgWaitTime: 0,
      } as QueueNodeData
    case 'decision':
      return {
        type: 'decision',
        decisionId: `decision-${Date.now()}`,
        label: 'Decision Gate',
        shape: 'diamond',
        condition: {
          type: 'report_status',
          passValue: 'pass',
          failValue: 'fail',
        },
        passOutput: '',
        failOutput: '',
      } as DecisionNodeData
    case 'code_snippet':
      if (extra.template === 'quality_subtasks') {
        return {
          type: 'code_snippet',
          snippetId: `snippet-${Date.now()}`,
          label: 'Quality Subtasks (coding_principles)',
          language: 'python',
          code: [
            '# Quality subtasks are generated server-side before QA.',
            '# This node documents the policy in the pipeline graph.',
            '# See config/qa_requirements.json and DirectorService._ensure_quality_subtasks().'
          ].join('\n'),
          timeout: 30,
          runOn: 'task_exit',
        } as CodeSnippetNodeData
      }
      return {
        type: 'code_snippet',
        snippetId: `snippet-${Date.now()}`,
        label: 'Code Snippet',
        language: 'python',
        code: '# Your code here\nprint("Hello, Pipeline!")',
        timeout: 60,
        runOn: 'manual',
      } as CodeSnippetNodeData
    case 'subtask':
      return {
        type: 'subtask',
        label: 'Subtask Template',
        triggerFrom: 'pm',
        triggerTo: 'dev',
        templatePath: extra.templatePath || 'config/qa_requirements.json',
        templateItems: [],
        useCustomTemplate: false,
        autoAssignStage: 'dev',
        inheritRequirements: true,
      } as SubtaskNodeData
    default:
      return {
        type: 'stage',
        stageId: 'dev',
        label: 'New Node',
        autoAdvance: true,
        requiresApproval: false,
        timeout: 3600,
      } as StageNodeData
  }
}

// Default pipeline for demo - exported for use by editor
export const defaultNodes: PipelineNode[] = [
  {
    id: 'stage-pm',
    type: 'stage',
    position: { x: 80, y: 140 },
    data: {
      type: 'stage',
      stageId: 'pm',
      label: 'Planning (PM)',
      autoAdvance: true,
      requiresApproval: false,
      timeout: 3600,
      taskCount: 0,
      status: 'idle',
    },
  },
  {
    id: 'subtask-template',
    type: 'subtask',
    position: { x: 420, y: 140 },
    data: {
      type: 'subtask',
      label: 'Subtask Template',
      triggerFrom: 'pm',
      triggerTo: 'dev',
      templatePath: 'config/qa_requirements.json',
      templateItems: [],
      useCustomTemplate: false,
      autoAssignStage: 'dev',
      inheritRequirements: true,
    },
  },
  {
    id: 'stage-dev',
    type: 'stage',
    position: { x: 760, y: 140 },
    data: {
      type: 'stage',
      stageId: 'dev',
      label: 'Development',
      autoAdvance: true,
      requiresApproval: false,
      timeout: 7200,
      taskCount: 2,
      status: 'processing',
    },
  },
  {
    id: 'snippet-quality',
    type: 'code_snippet',
    position: { x: 1100, y: 140 },
    data: {
      type: 'code_snippet',
      snippetId: 'quality-subtasks',
      label: 'Quality Subtasks (coding_principles)',
      language: 'python',
      code: [
        '# Quality subtasks are generated server-side before QA.',
        '# See config/qa_requirements.json.'
      ].join('\n'),
      timeout: 30,
      runOn: 'task_exit',
    },
  },
  {
    id: 'stage-qa',
    type: 'stage',
    position: { x: 1440, y: 140 },
    data: {
      type: 'stage',
      stageId: 'qa',
      label: 'QA Testing',
      autoAdvance: false,
      requiresApproval: false,
      timeout: 3600,
      taskCount: 1,
      status: 'idle',
    },
  },
  {
    id: 'decision-qa',
    type: 'decision',
    position: { x: 1780, y: 135 },
    data: {
      type: 'decision',
      decisionId: 'qa-gate',
      label: 'QA Gate',
      shape: 'diamond',
      condition: {
        type: 'report_status',
        passValue: 'pass',
        failValue: 'fail',
      },
      passOutput: 'stage-sec',
      failOutput: 'stage-dev',
    },
  },
  {
    id: 'stage-sec',
    type: 'stage',
    position: { x: 2120, y: 90 },
    data: {
      type: 'stage',
      stageId: 'sec',
      label: 'Security',
      autoAdvance: false,
      requiresApproval: false,
      timeout: 1800,
      taskCount: 0,
      status: 'idle',
    },
  },
  {
    id: 'stage-docs',
    type: 'stage',
    position: { x: 2460, y: 90 },
    data: {
      type: 'stage',
      stageId: 'docs',
      label: 'Documentation',
      autoAdvance: true,
      requiresApproval: false,
      timeout: 1800,
      taskCount: 0,
      status: 'idle',
    },
  },
  {
    id: 'stage-complete',
    type: 'stage',
    position: { x: 2800, y: 90 },
    data: {
      type: 'stage',
      stageId: 'complete',
      label: 'Complete',
      autoAdvance: false,
      requiresApproval: true,
      timeout: 0,
      taskCount: 3,
      status: 'idle',
    },
  },
  {
    id: 'queue-agents',
    type: 'queue',
    position: { x: 1440, y: 340 },
    data: {
      type: 'queue',
      queueId: 'agent-queue',
      label: 'Agent Queue',
      jobTypes: ['agent_run'],
      maxDepth: 10,
      depth: 2,
      avgWaitTime: 45,
    },
  },
]

export const defaultEdges: PipelineEdge[] = [
  { id: 'e1', source: 'stage-pm', target: 'subtask-template', animated: true },
  { id: 'e2', source: 'subtask-template', target: 'stage-dev', animated: true },
  { id: 'e3', source: 'stage-dev', target: 'snippet-quality', animated: true },
  { id: 'e4', source: 'snippet-quality', target: 'stage-qa', animated: true },
  { id: 'e5', source: 'stage-qa', target: 'decision-qa', animated: true },
  {
    id: 'e6',
    source: 'decision-qa',
    sourceHandle: 'pass',
    target: 'stage-sec',
    animated: true,
    style: { stroke: '#22c55e' },
  },
  {
    id: 'e7',
    source: 'decision-qa',
    sourceHandle: 'fail',
    target: 'stage-dev',
    animated: true,
    style: { stroke: '#ef4444' },
  },
  { id: 'e8', source: 'stage-sec', target: 'stage-docs', animated: true },
  { id: 'e9', source: 'stage-docs', target: 'stage-complete', animated: true },
]

// Inner component that uses useReactFlow (must be inside ReactFlowProvider)
function PipelineCanvasInner({
  nodes: externalNodes,
  edges: externalEdges,
  onNodesChange: onNodesChangeProp,
  onEdgesChange: onEdgesChangeProp,
  onNodeClick,
  onNodeAdd,
  readOnly = false,
}: PipelineCanvasProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const { screenToFlowPosition } = useReactFlow()

  // Use React Flow's internal state management
  const [nodes, setNodes, onNodesChange] = useNodesState(externalNodes as Node[])
  const [edges, setEdges, onEdgesChange] = useEdgesState(externalEdges as Edge[])

  // Sync when external nodes change (from parent)
  useEffect(() => {
    setNodes(externalNodes as Node[])
  }, [externalNodes, setNodes])

  useEffect(() => {
    setEdges(externalEdges as Edge[])
  }, [externalEdges, setEdges])

  const onConnect = useCallback(
    (params: Connection) => {
      if (readOnly) return
      const newEdge = { ...params, animated: true }
      setEdges((eds) => {
        const updated = addEdge(newEdge, eds)
        // Notify parent
        if (onEdgesChangeProp) {
          onEdgesChangeProp(updated as PipelineEdge[])
        }
        return updated
      })
    },
    [setEdges, readOnly, onEdgesChangeProp]
  )

  // Handle React Flow node changes (drag, resize, etc.)
  const handleNodesChange = useCallback(
    (changes: Parameters<typeof onNodesChange>[0]) => {
      onNodesChange(changes)
      // Notify parent after the change
      setNodes((currentNodes) => {
        if (onNodesChangeProp) {
          onNodesChangeProp(currentNodes as PipelineNode[])
        }
        return currentNodes
      })
    },
    [onNodesChange, onNodesChangeProp, setNodes]
  )

  // Handle React Flow edge changes
  const handleEdgesChange = useCallback(
    (changes: Parameters<typeof onEdgesChange>[0]) => {
      onEdgesChange(changes)
      setEdges((currentEdges) => {
        if (onEdgesChangeProp) {
          onEdgesChangeProp(currentEdges as PipelineEdge[])
        }
        return currentEdges
      })
    },
    [onEdgesChange, onEdgesChangeProp, setEdges]
  )

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (onNodeClick) {
        onNodeClick(node as PipelineNode)
      }
    },
    [onNodeClick]
  )

  // Handle drag over (allow drop)
  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  // Handle drop from palette
  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      if (readOnly) return

      const nodeType = event.dataTransfer.getData('nodeType')
      if (!nodeType) return

      // Get extra data based on node type
      const extra: Record<string, string> = {}
      if (nodeType === 'stage') {
        extra.stageId = event.dataTransfer.getData('stageId') || 'dev'
      } else if (nodeType === 'agent') {
        extra.roleId = event.dataTransfer.getData('roleId') || 'dev'
      } else if (nodeType === 'code_snippet') {
        extra.template = event.dataTransfer.getData('template') || ''
      } else if (nodeType === 'subtask') {
        extra.templatePath = event.dataTransfer.getData('templatePath') || 'config/qa_requirements.json'
      }

      // Calculate drop position in flow coordinates
      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })

      // Create new node
      const newNode: PipelineNode = {
        id: generateNodeId(nodeType),
        type: nodeType as PipelineNode['type'],
        position,
        data: createNodeData(nodeType, extra),
      }

      // Add node to canvas and notify parent with full list
      setNodes((nds) => {
        const updated = [...nds, newNode as Node]
        if (onNodesChangeProp) {
          onNodesChangeProp(updated as PipelineNode[])
        }
        return updated
      })

      // Also notify via onNodeAdd if provided
      if (onNodeAdd) {
        onNodeAdd(newNode)
      }
    },
    [screenToFlowPosition, setNodes, onNodeAdd, onNodesChangeProp, readOnly]
  )

  // Memoize node types
  const memoizedNodeTypes = useMemo(() => nodeTypes, [])

  return (
    <div className="h-full w-full" ref={reactFlowWrapper}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={readOnly ? undefined : handleNodesChange}
        onEdgesChange={readOnly ? undefined : handleEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onDrop={onDrop}
        onDragOver={onDragOver}
        nodeTypes={memoizedNodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2}
        defaultEdgeOptions={{
          animated: true,
          style: { strokeWidth: 2 },
        }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        <Controls showInteractive={!readOnly} />
        <MiniMap
          nodeColor={(node) => {
            switch (node.type) {
              case 'stage':
                return '#3b82f6'
              case 'agent':
                return '#10b981'
              case 'queue':
                return '#f59e0b'
              case 'decision':
                return '#8b5cf6'
              case 'code_snippet':
                return '#eab308'
              default:
                return '#6b7280'
            }
          }}
          maskColor="rgba(0, 0, 0, 0.1)"
        />
        <Panel position="top-left" className="bg-white/80 p-2 rounded shadow text-sm">
          <div className="flex items-center gap-4 flex-wrap">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-blue-500" /> Stage
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-green-500" /> Agent
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-orange-500" /> Queue
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-purple-500" /> Decision
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-yellow-500" /> Code
            </span>
          </div>
        </Panel>
      </ReactFlow>
    </div>
  )
}

// Wrapper component that provides ReactFlowProvider
export function PipelineCanvas(props: PipelineCanvasProps) {
  return (
    <ReactFlowProvider>
      <PipelineCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
