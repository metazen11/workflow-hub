'use client'

import { useState, useCallback, useEffect } from 'react'
import { PipelineCanvas, defaultNodes, defaultEdges } from '@/components/canvas/PipelineCanvas'
import { pipelineConfigs, projects, roleConfigs } from '@/lib/api/postgrest'
import type {
  PipelineNode,
  PipelineEdge,
  PipelineConfig,
  PipelineSettings,
  CanvasConfig,
  Project,
  RoleConfig,
  StageNodeData,
  AgentNodeData,
  QueueNodeData,
  DecisionNodeData,
  CodeSnippetNodeData,
  SubtaskNodeData,
  DynamicVariable,
  QualityRequirement,
} from '@/lib/api/types'

// Default canvas config
const defaultCanvasConfig: CanvasConfig = { zoom: 1, panX: 0, panY: 0 }

// Dynamic Variables Editor Component
function DynamicVariablesEditor({
  variables = [],
  onChange,
}: {
  variables: DynamicVariable[]
  onChange: (vars: DynamicVariable[]) => void
}) {
  const addVariable = () => {
    onChange([...variables, { name: '', description: '', defaultValue: '', required: false }])
  }

  const updateVariable = (index: number, field: keyof DynamicVariable, value: string | boolean) => {
    const updated = [...variables]
    updated[index] = { ...updated[index], [field]: value }
    onChange(updated)
  }

  const removeVariable = (index: number) => {
    onChange(variables.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="block text-xs text-gray-500 uppercase tracking-wide">
          Dynamic Variables
        </label>
        <button
          onClick={addVariable}
          className="text-xs text-blue-600 hover:text-blue-700"
        >
          + Add Variable
        </button>
      </div>
      {variables.length === 0 ? (
        <p className="text-xs text-gray-400 italic">No variables defined</p>
      ) : (
        <div className="space-y-3">
          {variables.map((v, i) => (
            <div key={i} className="bg-gray-50 p-2 rounded border border-gray-200">
              <div className="flex items-center justify-between mb-2">
                <input
                  type="text"
                  value={v.name}
                  onChange={(e) => updateVariable(i, 'name', e.target.value)}
                  placeholder="Variable name"
                  className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm font-mono"
                />
                <button
                  onClick={() => removeVariable(i)}
                  className="ml-2 text-red-500 hover:text-red-600 text-xs"
                >
                  Remove
                </button>
              </div>
              <input
                type="text"
                value={v.description || ''}
                onChange={(e) => updateVariable(i, 'description', e.target.value)}
                placeholder="Description"
                className="w-full px-2 py-1 border border-gray-300 rounded text-xs mb-1"
              />
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={v.defaultValue || ''}
                  onChange={(e) => updateVariable(i, 'defaultValue', e.target.value)}
                  placeholder="Default value"
                  className="flex-1 px-2 py-1 border border-gray-300 rounded text-xs"
                />
                <label className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={v.required || false}
                    onChange={(e) => updateVariable(i, 'required', e.target.checked)}
                  />
                  Required
                </label>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-gray-400">
        Use {'{{variableName}}'} in prompts to reference variables
      </p>
    </div>
  )
}

// Default pipeline settings
const defaultSettings: PipelineSettings = {
  pipeline: {
    name: 'Default Pipeline',
    description: '',
    autoStart: false,
    maxConcurrentTasks: 5,
  },
  director: {
    enabled: true,
    pollInterval: 30,
    enforceTDD: true,
    enforceDRY: true,
    enforceSecurity: true,
  },
}

export default function EditorPage() {
  // Pipeline config state
  const [configId, setConfigId] = useState<number | null>(null)
  const [configName, setConfigName] = useState('New Pipeline')
  const [configDescription, setConfigDescription] = useState('')
  const [projectId, setProjectId] = useState<number | null>(null)
  const [settings, setSettings] = useState<PipelineSettings>(defaultSettings)
  const [canvasConfig, setCanvasConfig] = useState<CanvasConfig>(defaultCanvasConfig)

  // Editor state
  const [selectedNode, setSelectedNode] = useState<PipelineNode | null>(null)
  const [nodes, setNodes] = useState<PipelineNode[]>(defaultNodes)
  const [edges, setEdges] = useState<PipelineEdge[]>(defaultEdges)

  // UI state
  const [projectList, setProjectList] = useState<Project[]>([])
  const [configList, setConfigList] = useState<PipelineConfig[]>([])
  const [roleConfigList, setRoleConfigList] = useState<RoleConfig[]>([])
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [showConfigModal, setShowConfigModal] = useState(false)
  const [qaTemplates, setQaTemplates] = useState<QualityRequirement[]>([])
  const [qaTemplatesError, setQaTemplatesError] = useState<string | null>(null)

  // Load projects, configs, and role configs on mount
  useEffect(() => {
    loadProjects()
    loadConfigs()
    loadRoleConfigs()
    loadQaTemplates()
  }, [])

  const loadProjects = async () => {
    try {
      const data = await projects.list()
      setProjectList(data)
    } catch (err) {
      console.error('Failed to load projects:', err)
    }
  }

  const loadConfigs = async () => {
    try {
      const data = await pipelineConfigs.list()
      setConfigList(data)
    } catch (err) {
      console.error('Failed to load configs:', err)
    }
  }

  const loadRoleConfigs = async () => {
    try {
      const data = await roleConfigs.list()
      setRoleConfigList(data)
    } catch (err) {
      console.error('Failed to load role configs:', err)
    }
  }

  const loadQaTemplates = async () => {
    try {
      setQaTemplatesError(null)
      const res = await fetch('/api/qa-requirements')
      if (!res.ok) {
        throw new Error('Failed to load QA templates')
      }
      const data = await res.json()
      if (Array.isArray(data)) {
        setQaTemplates(data)
      } else {
        setQaTemplates([])
      }
    } catch (err) {
      setQaTemplates([])
      setQaTemplatesError('Unable to load QA template library')
    }
  }

  // Get role config for a given role ID
  const getRoleConfig = useCallback((roleId: string): RoleConfig | undefined => {
    return roleConfigList.find(rc => rc.role === roleId)
  }, [roleConfigList])

  // Stage to agent role mapping (matches director_service.py)
  const STAGE_TO_AGENT: Record<string, string> = {
    pm: 'pm',
    dev: 'dev',
    qa: 'qa',
    sec: 'security',
    docs: 'docs',
    complete: 'cicd',
  }

  const handleNodeClick = useCallback((node: PipelineNode) => {
    setSelectedNode(node)
  }, [])

  const handleNodesChange = useCallback((newNodes: PipelineNode[]) => {
    setNodes(newNodes)
  }, [])

  const handleEdgesChange = useCallback((newEdges: PipelineEdge[]) => {
    setEdges(newEdges)
  }, [])

  useEffect(() => {
    if (!selectedNode) {
      return
    }
    const updated = nodes.find(node => node.id === selectedNode.id)
    if (!updated) {
      setSelectedNode(null)
      return
    }
    if (updated !== selectedNode) {
      setSelectedNode(updated)
    }
  }, [nodes, selectedNode])

  // Update a node's data property
  const updateNodeData = useCallback((nodeId: string, key: string, value: unknown) => {
    setNodes(prevNodes => {
      const updated = prevNodes.map(node => {
        if (node.id === nodeId) {
          return {
            ...node,
            data: {
              ...node.data,
              [key]: value,
            },
          }
        }
        return node
      })
      return updated
    })
  }, [])

  // Delete a node
  const deleteNode = useCallback((nodeId: string) => {
    setNodes(prevNodes => prevNodes.filter(n => n.id !== nodeId))
    setEdges(prevEdges => prevEdges.filter(e => e.source !== nodeId && e.target !== nodeId))
    setSelectedNode(null)
  }, [])

  // Load a specific config
  const loadConfig = async (id: number) => {
    setLoading(true)
    setMessage(null)
    try {
      const config = await pipelineConfigs.get(id)
      if (config) {
        setConfigId(config.id)
        setConfigName(config.name)
        setConfigDescription(config.description || '')
        setProjectId(config.project_id)
        setNodes(config.nodes || defaultNodes)
        setEdges(config.edges || defaultEdges)
        setSettings(config.settings || defaultSettings)
        setCanvasConfig(config.canvas_config || defaultCanvasConfig)
        setSelectedNode(null)
        setMessage({ type: 'success', text: `Loaded "${config.name}"` })
      }
    } catch (err) {
      console.error('Failed to load config:', err)
      setMessage({ type: 'error', text: 'Failed to load configuration' })
    } finally {
      setLoading(false)
    }
  }

  // Create a new pipeline (reset to defaults)
  const newPipeline = () => {
    setConfigId(null)
    setConfigName('New Pipeline')
    setConfigDescription('')
    setProjectId(null)
    setNodes(defaultNodes)
    setEdges(defaultEdges)
    setSettings(defaultSettings)
    setCanvasConfig(defaultCanvasConfig)
    setSelectedNode(null)
    setMessage(null)
  }

  // Save the current config
  const handleSave = async () => {
    if (!configName.trim()) {
      setMessage({ type: 'error', text: 'Please enter a pipeline name' })
      return
    }

    setSaving(true)
    setMessage(null)

    try {
      const configData = {
        name: configName.trim(),
        description: configDescription.trim() || undefined,
        project_id: projectId || undefined,
        nodes,
        edges,
        settings,
        canvas_config: canvasConfig,
        is_active: true,
      }

      if (configId) {
        // Update existing config
        await pipelineConfigs.update(configId, configData)
        setMessage({ type: 'success', text: `Updated "${configName}"` })
      } else {
        // Create new config
        const newConfig = await pipelineConfigs.create({
          ...configData,
          version: 1,
          created_by: 'user',
        })
        setConfigId(newConfig.id)
        setMessage({ type: 'success', text: `Created "${configName}"` })
      }

      // Refresh the config list
      await loadConfigs()
    } catch (err) {
      console.error('Failed to save config:', err)
      setMessage({ type: 'error', text: 'Failed to save configuration' })
    } finally {
      setSaving(false)
    }
  }

  // Delete the current config
  const handleDelete = async () => {
    if (!configId) return
    if (!confirm('Are you sure you want to delete this pipeline configuration?')) return

    setSaving(true)
    try {
      await pipelineConfigs.delete(configId)
      newPipeline()
      await loadConfigs()
      setMessage({ type: 'success', text: 'Pipeline deleted' })
    } catch (err) {
      console.error('Failed to delete config:', err)
      setMessage({ type: 'error', text: 'Failed to delete configuration' })
    } finally {
      setSaving(false)
    }
  }

  // Get typed data helpers
  const getStageData = (node: PipelineNode): StageNodeData | null =>
    node.type === 'stage' ? node.data as StageNodeData : null

  const getAgentData = (node: PipelineNode): AgentNodeData | null =>
    node.type === 'agent' ? node.data as AgentNodeData : null

  const getQueueData = (node: PipelineNode): QueueNodeData | null =>
    node.type === 'queue' ? node.data as QueueNodeData : null

  const getDecisionData = (node: PipelineNode): DecisionNodeData | null =>
    node.type === 'decision' ? node.data as DecisionNodeData : null

  const getCodeSnippetData = (node: PipelineNode): CodeSnippetNodeData | null =>
    node.type === 'code_snippet' ? node.data as CodeSnippetNodeData : null

  const getSubtaskData = (node: PipelineNode): SubtaskNodeData | null =>
    node.type === 'subtask' ? node.data as SubtaskNodeData : null

  return (
    <div className="flex h-[calc(100vh-56px)]">
      {/* Left Sidebar - Pipeline Config & Node Palette */}
      <div className="w-64 bg-white border-r border-gray-200 p-4 overflow-y-auto">
        {/* Message banner */}
        {message && (
          <div
            className={`mb-4 p-2 rounded text-sm ${
              message.type === 'success'
                ? 'bg-green-50 text-green-700 border border-green-200'
                : 'bg-red-50 text-red-700 border border-red-200'
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Pipeline Config Section */}
        <div className="mb-6">
          <h3 className="font-semibold text-gray-900 mb-3">Pipeline</h3>

          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                Name
              </label>
              <input
                type="text"
                value={configName}
                onChange={(e) => setConfigName(e.target.value)}
                placeholder="Pipeline name"
                className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                Project (optional)
              </label>
              <select
                value={projectId || ''}
                onChange={(e) => setProjectId(e.target.value ? parseInt(e.target.value) : null)}
                className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm"
              >
                <option value="">No project (template)</option>
                {projectList.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
              >
                {saving ? 'Saving...' : configId ? 'Update' : 'Save'}
              </button>
              <button
                onClick={newPipeline}
                className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 text-sm"
              >
                New
              </button>
            </div>

            {configId && (
              <button
                onClick={handleDelete}
                disabled={saving}
                className="w-full px-3 py-1.5 text-red-600 bg-red-50 border border-red-200 rounded hover:bg-red-100 text-sm disabled:opacity-50"
              >
                Delete Pipeline
              </button>
            )}
          </div>
        </div>

        {/* Saved Configs */}
        {configList.length > 0 && (
          <div className="mb-6">
            <h3 className="font-semibold text-gray-900 mb-3">Saved Pipelines</h3>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {configList.map((cfg) => (
                <button
                  key={cfg.id}
                  onClick={() => loadConfig(cfg.id)}
                  disabled={loading}
                  className={`w-full text-left px-3 py-2 rounded text-sm truncate ${
                    cfg.id === configId
                      ? 'bg-blue-100 text-blue-700 font-medium'
                      : 'bg-gray-50 hover:bg-gray-100 text-gray-700'
                  } disabled:opacity-50`}
                >
                  {cfg.name}
                  {cfg.project_id && (
                    <span className="text-gray-400 text-xs ml-1">
                      ({projectList.find((p) => p.id === cfg.project_id)?.name || 'project'})
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Node Palette */}
        <h3 className="font-semibold text-gray-900 mb-3">Add Nodes</h3>

        <div className="space-y-2">
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">
            Stages
          </div>
          {['pm', 'dev', 'qa', 'sec', 'docs', 'complete'].map((stage) => (
            <div
              key={stage}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('nodeType', 'stage')
                e.dataTransfer.setData('stageId', stage)
              }}
              className="p-2 bg-blue-50 border border-blue-200 rounded cursor-grab hover:bg-blue-100 text-sm"
            >
              {stage.toUpperCase()} Stage
            </div>
          ))}

          <div className="text-xs text-gray-500 uppercase tracking-wide mb-2 mt-4">
            Agents
          </div>
          {['pm', 'dev', 'qa', 'security', 'docs'].map((agent) => (
            <div
              key={agent}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('nodeType', 'agent')
                e.dataTransfer.setData('roleId', agent)
              }}
              className="p-2 bg-green-50 border border-green-200 rounded cursor-grab hover:bg-green-100 text-sm"
            >
              {agent.toUpperCase()} Agent
            </div>
          ))}

          <div className="text-xs text-gray-500 uppercase tracking-wide mb-2 mt-4">
            Other
          </div>
          <div
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('nodeType', 'subtask')
              e.dataTransfer.setData('templatePath', 'config/qa_requirements.json')
            }}
            className="p-2 bg-green-50 border border-green-200 rounded cursor-grab hover:bg-green-100 text-sm"
          >
            🧩 Subtask Template (PM → DEV)
          </div>
          <div
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('nodeType', 'code_snippet')
              e.dataTransfer.setData('template', 'quality_subtasks')
            }}
            className="p-2 bg-yellow-50 border border-yellow-200 rounded cursor-grab hover:bg-yellow-100 text-sm"
          >
            ✅ Quality Subtasks (coding_principles)
          </div>
          <div
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('nodeType', 'queue')
            }}
            className="p-2 bg-orange-50 border border-orange-200 rounded cursor-grab hover:bg-orange-100 text-sm"
          >
            Job Queue
          </div>
          <div
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('nodeType', 'decision')
            }}
            className="p-2 bg-purple-50 border border-purple-200 rounded cursor-grab hover:bg-purple-100 text-sm"
          >
            Decision Gate
          </div>
          <div
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('nodeType', 'code_snippet')
            }}
            className="p-2 bg-yellow-50 border border-yellow-200 rounded cursor-grab hover:bg-yellow-100 text-sm"
          >
            Code Snippet
          </div>
        </div>
      </div>

      {/* Main Canvas */}
      <div className="flex-1">
        <PipelineCanvas
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onNodeClick={handleNodeClick}
        />
      </div>

      {/* Right Sidebar - Node Properties */}
      <div className="w-80 bg-white border-l border-gray-200 p-4 overflow-y-auto">
        <h3 className="font-semibold text-gray-900 mb-4">Properties</h3>

        {selectedNode ? (
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                Node Type
              </label>
              <div className="text-sm font-medium text-gray-900 capitalize">
                {selectedNode.type}
              </div>
            </div>

            <div>
              <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                ID
              </label>
              <div className="text-sm font-mono text-gray-600">
                {selectedNode.id}
              </div>
            </div>

            <div>
              <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                Label
              </label>
              <input
                type="text"
                value={selectedNode.data.label || ''}
                onChange={(e) => updateNodeData(selectedNode.id, 'label', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
              />
            </div>

            {/* Stage-specific properties */}
            {selectedNode.type === 'stage' && (() => {
              const data = getStageData(selectedNode)
              if (!data) return null
              return (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Stage ID
                    </label>
                    <select
                      value={data.stageId}
                      onChange={(e) => updateNodeData(selectedNode.id, 'stageId', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="pm">PM (Planning)</option>
                      <option value="dev">DEV (Development)</option>
                      <option value="qa">QA (Testing)</option>
                      <option value="sec">SEC (Security)</option>
                      <option value="docs">DOCS (Documentation)</option>
                      <option value="complete">COMPLETE</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Timeout (seconds)
                    </label>
                    <input
                      type="number"
                      value={data.timeout}
                      onChange={(e) => updateNodeData(selectedNode.id, 'timeout', parseInt(e.target.value) || 0)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="autoAdvance"
                      checked={data.autoAdvance}
                      onChange={(e) => updateNodeData(selectedNode.id, 'autoAdvance', e.target.checked)}
                    />
                    <label htmlFor="autoAdvance" className="text-sm text-gray-700">
                      Auto-advance to next stage
                    </label>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="requiresApproval"
                      checked={data.requiresApproval}
                      onChange={(e) => updateNodeData(selectedNode.id, 'requiresApproval', e.target.checked)}
                    />
                    <label htmlFor="requiresApproval" className="text-sm text-gray-700">
                      Requires human approval
                    </label>
                  </div>

                  {/* Show associated agent role from role_configs */}
                  {(() => {
                    const agentRole = STAGE_TO_AGENT[data.stageId]
                    const roleConfig = agentRole ? getRoleConfig(agentRole) : undefined
                    return (
                      <div className="bg-blue-50 border border-blue-200 rounded p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-semibold text-blue-700 uppercase">
                            Agent: {roleConfig?.name || agentRole?.toUpperCase() || 'None'}
                          </span>
                          {roleConfig && (
                            <span className={`text-xs px-2 py-0.5 rounded ${roleConfig.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                              {roleConfig.active ? 'Active' : 'Inactive'}
                            </span>
                          )}
                        </div>
                        {roleConfig?.description && (
                          <p className="text-xs text-blue-600 mb-2">{roleConfig.description}</p>
                        )}
                        {roleConfig && (
                          <div className="text-xs text-gray-500">
                            Base prompt: {roleConfig.prompt?.length || 0} chars
                            {roleConfig.requires_approval && (
                              <span className="ml-2 text-orange-600">(Requires Approval)</span>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })()}

                  <div className="pt-3 border-t border-gray-200">
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                      Stage Prompts (Override Agent Default)
                    </h4>
                    <p className="text-xs text-gray-400 mb-2">
                      Leave empty to use base agent prompt. Add text to extend/override.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Entry Prompt
                    </label>
                    <textarea
                      rows={3}
                      value={data.entryPrompt || ''}
                      onChange={(e) => updateNodeData(selectedNode.id, 'entryPrompt', e.target.value || undefined)}
                      placeholder="Additional prompt when task enters this stage..."
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Exit Prompt
                    </label>
                    <textarea
                      rows={3}
                      value={data.exitPrompt || ''}
                      onChange={(e) => updateNodeData(selectedNode.id, 'exitPrompt', e.target.value || undefined)}
                      placeholder="Prompt executed when task exits this stage..."
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Validation Rules (one per line)
                    </label>
                    <textarea
                      rows={3}
                      value={(data.validationRules || []).join('\n')}
                      onChange={(e) => updateNodeData(
                        selectedNode.id,
                        'validationRules',
                        e.target.value ? e.target.value.split('\n').filter(r => r.trim()) : undefined
                      )}
                      placeholder="all_tests_pass&#10;no_security_issues&#10;code_coverage > 80%"
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                    />
                  </div>

                  <DynamicVariablesEditor
                    variables={data.variables || []}
                    onChange={(vars) => updateNodeData(selectedNode.id, 'variables', vars.length > 0 ? vars : undefined)}
                  />
                </>
              )
            })()}

            {/* Agent-specific properties */}
            {selectedNode.type === 'agent' && (() => {
              const data = getAgentData(selectedNode)
              if (!data) return null
              return (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Role
                    </label>
                    <select
                      value={data.roleId}
                      onChange={(e) => updateNodeData(selectedNode.id, 'roleId', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="director">Director</option>
                      <option value="pm">PM</option>
                      <option value="dev">DEV</option>
                      <option value="qa">QA</option>
                      <option value="security">Security</option>
                      <option value="docs">Docs</option>
                      <option value="cicd">CI/CD</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Priority
                    </label>
                    <select
                      value={data.priority}
                      onChange={(e) => updateNodeData(selectedNode.id, 'priority', parseInt(e.target.value))}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="1">Critical (1)</option>
                      <option value="2">High (2)</option>
                      <option value="3">Normal (3)</option>
                      <option value="4">Low (4)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Timeout (seconds)
                    </label>
                    <input
                      type="number"
                      value={data.timeout}
                      onChange={(e) => updateNodeData(selectedNode.id, 'timeout', parseInt(e.target.value) || 0)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Concurrency
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={data.concurrency}
                      onChange={(e) => updateNodeData(selectedNode.id, 'concurrency', parseInt(e.target.value) || 1)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  {/* Show base role config from database */}
                  {(() => {
                    const roleConfig = getRoleConfig(data.roleId)
                    return (
                      <div className="bg-green-50 border border-green-200 rounded p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-semibold text-green-700 uppercase">
                            Base Config: {roleConfig?.name || data.roleId}
                          </span>
                          {roleConfig && (
                            <span className={`text-xs px-2 py-0.5 rounded ${roleConfig.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                              {roleConfig.active ? 'Active' : 'Inactive'}
                            </span>
                          )}
                        </div>
                        {roleConfig?.description && (
                          <p className="text-xs text-green-600 mb-2">{roleConfig.description}</p>
                        )}
                        {roleConfig && (
                          <>
                            <div className="text-xs text-gray-500 mb-2">
                              Base prompt: {roleConfig.prompt?.length || 0} chars
                              {roleConfig.requires_approval && (
                                <span className="ml-2 text-orange-600">(Requires Approval)</span>
                              )}
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                if (confirm('Load base prompt from role config? This will replace any current override.')) {
                                  updateNodeData(selectedNode.id, 'promptOverride', roleConfig.prompt)
                                }
                              }}
                              className="text-xs text-green-700 hover:text-green-800 underline"
                            >
                              Load Base Prompt into Override
                            </button>
                          </>
                        )}
                        {!roleConfig && (
                          <p className="text-xs text-orange-600">
                            No config found for role &quot;{data.roleId}&quot;. Check role_configs table.
                          </p>
                        )}
                      </div>
                    )
                  })()}

                  <div className="pt-3 border-t border-gray-200">
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                      Prompt Customization
                    </h4>
                    <p className="text-xs text-gray-400 mb-2">
                      Leave empty to use base prompt. Use prefix/suffix to extend, or override to replace entirely.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Prompt Override (full replacement)
                    </label>
                    <textarea
                      rows={3}
                      value={data.promptOverride || ''}
                      onChange={(e) => updateNodeData(selectedNode.id, 'promptOverride', e.target.value || undefined)}
                      placeholder="Leave empty to use base prompt with prefix/suffix..."
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Prompt Prefix
                    </label>
                    <textarea
                      rows={2}
                      value={data.promptPrefix || ''}
                      onChange={(e) => updateNodeData(selectedNode.id, 'promptPrefix', e.target.value || undefined)}
                      placeholder="Text added before base prompt..."
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Prompt Suffix
                    </label>
                    <textarea
                      rows={2}
                      value={data.promptSuffix || ''}
                      onChange={(e) => updateNodeData(selectedNode.id, 'promptSuffix', e.target.value || undefined)}
                      placeholder="Text added after base prompt..."
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      System Context
                    </label>
                    <textarea
                      rows={2}
                      value={data.systemContext || ''}
                      onChange={(e) => updateNodeData(selectedNode.id, 'systemContext', e.target.value || undefined)}
                      placeholder="Additional system-level instructions..."
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div className="pt-3 border-t border-gray-200">
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                      Retry Settings
                    </h4>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                        Max Retries
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="10"
                        value={data.maxRetries ?? 3}
                        onChange={(e) => updateNodeData(selectedNode.id, 'maxRetries', parseInt(e.target.value) || 0)}
                        className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                        Retry Delay (ms)
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="1000"
                        value={data.retryDelay ?? 5000}
                        onChange={(e) => updateNodeData(selectedNode.id, 'retryDelay', parseInt(e.target.value) || 0)}
                        className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                      />
                    </div>
                  </div>

                  <DynamicVariablesEditor
                    variables={data.variables || []}
                    onChange={(vars) => updateNodeData(selectedNode.id, 'variables', vars.length > 0 ? vars : undefined)}
                  />
                </>
              )
            })()}

            {/* Queue-specific properties */}
            {selectedNode.type === 'queue' && (() => {
              const data = getQueueData(selectedNode)
              if (!data) return null
              return (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Queue ID
                    </label>
                    <input
                      type="text"
                      value={data.queueId}
                      onChange={(e) => updateNodeData(selectedNode.id, 'queueId', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Max Depth
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={data.maxDepth}
                      onChange={(e) => updateNodeData(selectedNode.id, 'maxDepth', parseInt(e.target.value) || 10)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Job Types
                    </label>
                    <div className="space-y-1">
                      {['llm_complete', 'llm_chat', 'llm_query', 'vision_analyze', 'agent_run'].map(jt => (
                        <label key={jt} className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={data.jobTypes.includes(jt as typeof data.jobTypes[number])}
                            onChange={(e) => {
                              const newTypes = e.target.checked
                                ? [...data.jobTypes, jt]
                                : data.jobTypes.filter(t => t !== jt)
                              updateNodeData(selectedNode.id, 'jobTypes', newTypes)
                            }}
                          />
                          {jt.replace('_', ' ')}
                        </label>
                      ))}
                    </div>
                  </div>
                </>
              )
            })()}

            {/* Decision-specific properties */}
            {selectedNode.type === 'decision' && (() => {
              const data = getDecisionData(selectedNode)
              if (!data) return null
              return (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Condition Type
                    </label>
                    <select
                      value={data.condition.type}
                      onChange={(e) => updateNodeData(selectedNode.id, 'condition', {
                        ...data.condition,
                        type: e.target.value,
                      })}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="report_status">Report Status</option>
                      <option value="manual_approval">Manual Approval</option>
                      <option value="custom">Custom (LLM)</option>
                      <option value="script">Script</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Pass Value
                    </label>
                    <input
                      type="text"
                      value={data.condition.passValue}
                      onChange={(e) => updateNodeData(selectedNode.id, 'condition', {
                        ...data.condition,
                        passValue: e.target.value,
                      })}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Fail Value
                    </label>
                    <input
                      type="text"
                      value={data.condition.failValue}
                      onChange={(e) => updateNodeData(selectedNode.id, 'condition', {
                        ...data.condition,
                        failValue: e.target.value,
                      })}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Shape
                    </label>
                    <select
                      value={data.shape}
                      onChange={(e) => updateNodeData(selectedNode.id, 'shape', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="diamond">Diamond</option>
                      <option value="hexagon">Hexagon</option>
                    </select>
                  </div>

                  {/* Script/Custom condition fields */}
                  {data.condition.type === 'script' && (
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                        Condition Script
                      </label>
                      <textarea
                        rows={5}
                        value={data.condition.customScript || ''}
                        onChange={(e) => updateNodeData(selectedNode.id, 'condition', {
                          ...data.condition,
                          customScript: e.target.value || undefined,
                        })}
                        placeholder="# Python/JS code that returns True/False&#10;return task.status == 'pass'"
                        className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                      />
                      <p className="text-xs text-gray-400 mt-1">
                        Available vars: task, context, prev_output
                      </p>
                    </div>
                  )}

                  {data.condition.type === 'custom' && (
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                        LLM Condition Prompt
                      </label>
                      <textarea
                        rows={4}
                        value={data.condition.customPrompt || ''}
                        onChange={(e) => updateNodeData(selectedNode.id, 'condition', {
                          ...data.condition,
                          customPrompt: e.target.value || undefined,
                        })}
                        placeholder="Evaluate if the task should pass or fail based on..."
                        className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                      />
                      <p className="text-xs text-gray-400 mt-1">
                        LLM will respond with pass/fail value
                      </p>
                    </div>
                  )}

                  {/* Manual approval fields */}
                  {data.condition.type === 'manual_approval' && (
                    <>
                      <div className="pt-3 border-t border-gray-200">
                        <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                          Approval Settings
                        </h4>
                      </div>

                      <div>
                        <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                          Approval Prompt
                        </label>
                        <textarea
                          rows={2}
                          value={data.approvalPrompt || ''}
                          onChange={(e) => updateNodeData(selectedNode.id, 'approvalPrompt', e.target.value || undefined)}
                          placeholder="Please review and approve this task..."
                          className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                        />
                      </div>

                      <div>
                        <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                          Approval Instructions
                        </label>
                        <textarea
                          rows={3}
                          value={data.approvalInstructions || ''}
                          onChange={(e) => updateNodeData(selectedNode.id, 'approvalInstructions', e.target.value || undefined)}
                          placeholder="Check the following before approving:&#10;- Code review complete&#10;- Tests passing"
                          className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                        />
                      </div>
                    </>
                  )}

                  <DynamicVariablesEditor
                    variables={data.variables || []}
                    onChange={(vars) => updateNodeData(selectedNode.id, 'variables', vars.length > 0 ? vars : undefined)}
                  />
                </>
              )
            })()}

            {/* Code Snippet-specific properties */}
            {selectedNode.type === 'code_snippet' && (() => {
              const data = getCodeSnippetData(selectedNode)
              if (!data) return null
              return (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Language
                    </label>
                    <select
                      value={data.language}
                      onChange={(e) => updateNodeData(selectedNode.id, 'language', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="python">Python</option>
                      <option value="bash">Bash</option>
                      <option value="javascript">JavaScript</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Run Trigger
                    </label>
                    <select
                      value={data.runOn}
                      onChange={(e) => updateNodeData(selectedNode.id, 'runOn', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="task_enter">On Task Enter</option>
                      <option value="task_exit">On Task Exit</option>
                      <option value="manual">Manual</option>
                      <option value="schedule">Scheduled (cron)</option>
                    </select>
                  </div>

                  {data.runOn === 'schedule' && (
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                        Cron Schedule
                      </label>
                      <input
                        type="text"
                        value={data.schedule || ''}
                        onChange={(e) => updateNodeData(selectedNode.id, 'schedule', e.target.value)}
                        placeholder="*/5 * * * *"
                        className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                      />
                    </div>
                  )}

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Timeout (seconds)
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="3600"
                      value={data.timeout}
                      onChange={(e) => updateNodeData(selectedNode.id, 'timeout', parseInt(e.target.value) || 60)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Code
                    </label>
                    <textarea
                      rows={10}
                      value={data.code}
                      onChange={(e) => updateNodeData(selectedNode.id, 'code', e.target.value)}
                      placeholder="# Your code here..."
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Available vars: task, project, context, prev_output
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Output Variable Name
                    </label>
                    <input
                      type="text"
                      value={data.outputVar || ''}
                      onChange={(e) => updateNodeData(selectedNode.id, 'outputVar', e.target.value)}
                      placeholder="result"
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                    />
                  </div>

                  <div className="pt-3 border-t border-gray-200">
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                      Pass/Fail Behavior
                    </h4>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="canFail"
                      checked={data.canFail || false}
                      onChange={(e) => updateNodeData(selectedNode.id, 'canFail', e.target.checked)}
                    />
                    <label htmlFor="canFail" className="text-sm text-gray-700">
                      Can signal pass/fail
                    </label>
                  </div>

                  {data.canFail && (
                    <>
                      <div>
                        <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                          Fail Detection
                        </label>
                        <select
                          value={data.failOn || 'exit_code'}
                          onChange={(e) => updateNodeData(selectedNode.id, 'failOn', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                        >
                          <option value="exit_code">Non-zero exit code</option>
                          <option value="output">Output pattern match</option>
                          <option value="exception">Uncaught exception</option>
                        </select>
                      </div>

                      {data.failOn === 'output' && (
                        <div>
                          <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                            Fail Pattern (regex)
                          </label>
                          <input
                            type="text"
                            value={data.failPattern || ''}
                            onChange={(e) => updateNodeData(selectedNode.id, 'failPattern', e.target.value || undefined)}
                            placeholder="error|fail|FAILED"
                            className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                          />
                        </div>
                      )}

                      <div>
                        <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                          On Failure
                        </label>
                        <select
                          value={data.onFailAction || 'stop'}
                          onChange={(e) => updateNodeData(selectedNode.id, 'onFailAction', e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                        >
                          <option value="stop">Stop pipeline</option>
                          <option value="continue">Continue anyway</option>
                          <option value="route">Route to another node</option>
                        </select>
                      </div>

                      {data.onFailAction === 'route' && (
                        <div>
                          <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                            Fail Route Target (Node ID)
                          </label>
                          <input
                            type="text"
                            value={data.failRouteTarget || ''}
                            onChange={(e) => updateNodeData(selectedNode.id, 'failRouteTarget', e.target.value || undefined)}
                            placeholder="stage-dev"
                            className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                          />
                        </div>
                      )}
                    </>
                  )}

                  <DynamicVariablesEditor
                    variables={data.variables || []}
                    onChange={(vars) => updateNodeData(selectedNode.id, 'variables', vars.length > 0 ? vars : undefined)}
                  />

                  {data.lastRunAt && (
                    <div className="text-xs text-gray-500 bg-gray-50 p-2 rounded">
                      Last run: {new Date(data.lastRunAt).toLocaleString()}
                      <span className={`ml-2 ${
                        data.lastRunStatus === 'success' ? 'text-green-600' :
                        data.lastRunStatus === 'error' ? 'text-red-600' :
                        'text-orange-600'
                      }`}>
                        ({data.lastRunStatus})
                      </span>
                    </div>
                  )}
                </>
              )
            })()}

            {selectedNode.type === 'subtask' && (() => {
              const data = getSubtaskData(selectedNode)
              if (!data) return null
              return (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Trigger From
                    </label>
                    <select
                      value={data.triggerFrom}
                      onChange={(e) => updateNodeData(selectedNode.id, 'triggerFrom', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="pm">PM</option>
                      <option value="dev">DEV</option>
                      <option value="qa">QA</option>
                      <option value="sec">SEC</option>
                      <option value="docs">DOCS</option>
                      <option value="complete">COMPLETE</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Trigger To
                    </label>
                    <select
                      value={data.triggerTo}
                      onChange={(e) => updateNodeData(selectedNode.id, 'triggerTo', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="pm">PM</option>
                      <option value="dev">DEV</option>
                      <option value="qa">QA</option>
                      <option value="sec">SEC</option>
                      <option value="docs">DOCS</option>
                      <option value="complete">COMPLETE</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Template Source
                    </label>
                    <select
                      value={data.useCustomTemplate ? 'custom' : 'path'}
                      onChange={(e) => updateNodeData(selectedNode.id, 'useCustomTemplate', e.target.value === 'custom')}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="path">File path</option>
                      <option value="custom">Custom list</option>
                    </select>
                  </div>

                  {!data.useCustomTemplate && (
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                        Template Path
                      </label>
                      <input
                        type="text"
                        value={data.templatePath}
                        onChange={(e) => updateNodeData(selectedNode.id, 'templatePath', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                      />
                    </div>
                  )}

                  {data.useCustomTemplate && (() => {
                    const items = data.templateItems || []
                    const updateItems = (next: QualityRequirement[]) => {
                      updateNodeData(selectedNode.id, 'templateItems', next)
                    }
                    const updateItem = (index: number, field: keyof QualityRequirement, value: string | string[]) => {
                      const next = items.map((item, i) => {
                        if (i !== index) return item
                        return { ...item, [field]: value }
                      })
                      updateItems(next)
                    }
                    const addItem = () => {
                      updateItems([
                        ...items,
                        {
                          id: `REQ-${Date.now()}`,
                          title: '',
                          subtask_title: '',
                          description: '',
                          acceptance_criteria: [],
                        },
                      ])
                    }
                    const removeItem = (index: number) => {
                      updateItems(items.filter((_, i) => i !== index))
                    }
                    const loadDefaults = () => {
                      if (qaTemplates.length === 0) {
                        return
                      }
                      updateItems(qaTemplates)
                    }

                    return (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <label className="block text-xs text-gray-500 uppercase tracking-wide">
                            Template Items ({items.length})
                          </label>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={loadDefaults}
                              className="text-xs text-blue-600 hover:text-blue-700"
                              disabled={qaTemplates.length === 0}
                            >
                              Load defaults
                            </button>
                            <button
                              onClick={addItem}
                              className="text-xs text-blue-600 hover:text-blue-700"
                            >
                              + Add item
                            </button>
                          </div>
                        </div>
                        {qaTemplatesError && (
                          <div className="text-xs text-red-600">{qaTemplatesError}</div>
                        )}
                        {items.length === 0 ? (
                          <div className="text-xs text-gray-400 italic">
                            No template items defined yet.
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {items.map((item, index) => (
                              <div key={`${item.id}-${index}`} className="bg-gray-50 border border-gray-200 rounded p-3 space-y-2">
                                <div className="flex items-center gap-2">
                                  <input
                                    type="text"
                                    value={item.id || ''}
                                    onChange={(e) => updateItem(index, 'id', e.target.value)}
                                    placeholder="Requirement ID"
                                    className="flex-1 px-2 py-1 border border-gray-300 rounded text-xs font-mono"
                                  />
                                  <button
                                    onClick={() => removeItem(index)}
                                    className="text-xs text-red-500 hover:text-red-600"
                                  >
                                    Remove
                                  </button>
                                </div>
                                <input
                                  type="text"
                                  value={item.title || ''}
                                  onChange={(e) => updateItem(index, 'title', e.target.value)}
                                  placeholder="Title"
                                  className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                                />
                                <input
                                  type="text"
                                  value={item.subtask_title || ''}
                                  onChange={(e) => updateItem(index, 'subtask_title', e.target.value)}
                                  placeholder="Subtask title"
                                  className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                                />
                                <textarea
                                  value={item.description || ''}
                                  onChange={(e) => updateItem(index, 'description', e.target.value)}
                                  placeholder="Description"
                                  className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                                  rows={2}
                                />
                                <textarea
                                  value={(item.acceptance_criteria || []).join('\n')}
                                  onChange={(e) => {
                                    const lines = e.target.value
                                      .split('\n')
                                      .map(line => line.trim())
                                      .filter(Boolean)
                                    updateItem(index, 'acceptance_criteria', lines)
                                  }}
                                  placeholder="Acceptance criteria (one per line)"
                                  className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                                  rows={3}
                                />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })()}

                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wide mb-1">
                      Auto Assign Stage
                    </label>
                    <select
                      value={data.autoAssignStage}
                      onChange={(e) => updateNodeData(selectedNode.id, 'autoAssignStage', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    >
                      <option value="pm">PM</option>
                      <option value="dev">DEV</option>
                      <option value="qa">QA</option>
                      <option value="sec">SEC</option>
                      <option value="docs">DOCS</option>
                      <option value="complete">COMPLETE</option>
                    </select>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="inheritRequirements"
                      checked={data.inheritRequirements}
                      onChange={(e) => updateNodeData(selectedNode.id, 'inheritRequirements', e.target.checked)}
                    />
                    <label htmlFor="inheritRequirements" className="text-sm text-gray-700">
                      Inherit parent requirements
                    </label>
                  </div>
                </>
              )
            })()}

            <div className="pt-4 border-t border-gray-200">
              <button
                onClick={() => deleteNode(selectedNode.id)}
                className="w-full px-4 py-2 bg-red-50 text-red-600 border border-red-200 rounded hover:bg-red-100 text-sm"
              >
                Delete Node
              </button>
            </div>
          </div>
        ) : (
          <div className="text-sm text-gray-500">
            Click a node to edit its properties
          </div>
        )}
      </div>
    </div>
  )
}
