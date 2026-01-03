'use client'

import { useState, useEffect, useCallback } from 'react'
import { roleConfigs, directorSettings } from '@/lib/api/postgrest'
import type { RoleConfig, DirectorSettings } from '@/lib/api/types'

export default function SettingsPage() {
  const [roles, setRoles] = useState<RoleConfig[]>([])
  const [director, setDirector] = useState<DirectorSettings | null>(null)
  const [selectedRole, setSelectedRole] = useState<RoleConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Form state for editing
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editPrompt, setEditPrompt] = useState('')
  const [editActive, setEditActive] = useState(true)
  const [editRequiresApproval, setEditRequiresApproval] = useState(false)

  // Director form state
  const [directorEnabled, setDirectorEnabled] = useState(true)
  const [directorPollInterval, setDirectorPollInterval] = useState(30)
  const [directorTDD, setDirectorTDD] = useState(true)
  const [directorDRY, setDirectorDRY] = useState(true)
  const [directorSecurity, setDirectorSecurity] = useState(true)

  // Load data
  const loadData = useCallback(async () => {
    try {
      const [rolesData, directorData] = await Promise.all([
        roleConfigs.list(),
        directorSettings.get(),
      ])
      setRoles(rolesData)
      setDirector(directorData)

      // Set director form state
      if (directorData) {
        setDirectorEnabled(directorData.enabled)
        setDirectorPollInterval(directorData.poll_interval)
        setDirectorTDD(directorData.enforce_tdd)
        setDirectorDRY(directorData.enforce_dry)
        setDirectorSecurity(directorData.enforce_security)
      }
    } catch (err) {
      console.error('Failed to load settings:', err)
      setMessage({ type: 'error', text: 'Failed to load settings' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Select a role for editing
  const selectRole = (role: RoleConfig) => {
    setSelectedRole(role)
    setEditName(role.name)
    setEditDescription(role.description || '')
    setEditPrompt(role.prompt)
    setEditActive(role.active)
    setEditRequiresApproval(role.requires_approval)
    setMessage(null)
  }

  // Save role changes
  const saveRole = async () => {
    if (!selectedRole) return

    setSaving(true)
    setMessage(null)

    try {
      await roleConfigs.update(selectedRole.role, {
        name: editName,
        description: editDescription || undefined,
        prompt: editPrompt,
        active: editActive,
        requires_approval: editRequiresApproval,
      })
      setMessage({ type: 'success', text: `Updated ${editName}` })
      await loadData()
      // Update selected role with new values
      const updated = roles.find(r => r.role === selectedRole.role)
      if (updated) setSelectedRole(updated)
    } catch (err) {
      console.error('Failed to save role:', err)
      setMessage({ type: 'error', text: 'Failed to save changes' })
    } finally {
      setSaving(false)
    }
  }

  // Save director settings
  const saveDirector = async () => {
    setSaving(true)
    setMessage(null)

    try {
      await directorSettings.update({
        enabled: directorEnabled,
        poll_interval: directorPollInterval,
        enforce_tdd: directorTDD,
        enforce_dry: directorDRY,
        enforce_security: directorSecurity,
      })
      setMessage({ type: 'success', text: 'Director settings updated' })
      await loadData()
    } catch (err) {
      console.error('Failed to save director settings:', err)
      setMessage({ type: 'error', text: 'Failed to save director settings' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-56px)]">
        <div className="text-gray-500">Loading settings...</div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

      {/* Message banner */}
      {message && (
        <div
          className={`mb-6 p-3 rounded ${
            message.type === 'success'
              ? 'bg-green-50 text-green-700 border border-green-200'
              : 'bg-red-50 text-red-700 border border-red-200'
          }`}
        >
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Agent List */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h2 className="font-semibold text-gray-900 mb-4">Agent Roles</h2>
            <div className="space-y-2">
              {roles.map(role => (
                <button
                  key={role.role}
                  onClick={() => selectRole(role)}
                  className={`w-full text-left p-3 rounded border transition-all ${
                    selectedRole?.role === role.role
                      ? 'bg-blue-50 border-blue-300 ring-2 ring-blue-200'
                      : 'bg-gray-50 border-gray-200 hover:bg-gray-100'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{role.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      role.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                    }`}>
                      {role.active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{role.role}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Director Settings */}
          <div className="bg-white rounded-lg border border-gray-200 p-4 mt-6">
            <h2 className="font-semibold text-gray-900 mb-4">Director Settings</h2>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="text-sm text-gray-700">Enabled</label>
                <input
                  type="checkbox"
                  checked={directorEnabled}
                  onChange={(e) => setDirectorEnabled(e.target.checked)}
                  className="rounded"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-700 mb-1">Poll Interval (seconds)</label>
                <input
                  type="number"
                  min="5"
                  max="300"
                  value={directorPollInterval}
                  onChange={(e) => setDirectorPollInterval(parseInt(e.target.value) || 30)}
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                />
              </div>

              <div className="space-y-2">
                <label className="block text-sm text-gray-700">Enforcement</label>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="tdd"
                    checked={directorTDD}
                    onChange={(e) => setDirectorTDD(e.target.checked)}
                  />
                  <label htmlFor="tdd" className="text-sm">TDD (Test-Driven Development)</label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="dry"
                    checked={directorDRY}
                    onChange={(e) => setDirectorDRY(e.target.checked)}
                  />
                  <label htmlFor="dry" className="text-sm">DRY (Don&apos;t Repeat Yourself)</label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="security"
                    checked={directorSecurity}
                    onChange={(e) => setDirectorSecurity(e.target.checked)}
                  />
                  <label htmlFor="security" className="text-sm">Security Checks</label>
                </div>
              </div>

              <button
                onClick={saveDirector}
                disabled={saving}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Director Settings'}
              </button>
            </div>
          </div>
        </div>

        {/* Right Column - Role Editor */}
        <div className="lg:col-span-2">
          {selectedRole ? (
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-6">
                <h2 className="font-semibold text-gray-900 text-lg">
                  Edit: {selectedRole.name}
                </h2>
                <span className="text-sm text-gray-500 font-mono">{selectedRole.role}</span>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Display Name
                  </label>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <input
                    type="text"
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    placeholder="Brief description of this agent's role"
                    className="w-full px-3 py-2 border border-gray-300 rounded"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    System Prompt
                  </label>
                  <textarea
                    rows={12}
                    value={editPrompt}
                    onChange={(e) => setEditPrompt(e.target.value)}
                    placeholder="The system prompt for this agent..."
                    className="w-full px-3 py-2 border border-gray-300 rounded font-mono text-sm"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    This prompt defines how the agent behaves. Use placeholders like {'{task}'}, {'{context}'}, {'{requirements}'}.
                  </p>
                </div>

                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="active"
                      checked={editActive}
                      onChange={(e) => setEditActive(e.target.checked)}
                    />
                    <label htmlFor="active" className="text-sm text-gray-700">
                      Active (available for assignment)
                    </label>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="requiresApproval"
                      checked={editRequiresApproval}
                      onChange={(e) => setEditRequiresApproval(e.target.checked)}
                    />
                    <label htmlFor="requiresApproval" className="text-sm text-gray-700">
                      Requires human approval
                    </label>
                  </div>
                </div>

                <div className="flex gap-3 pt-4 border-t">
                  <button
                    onClick={saveRole}
                    disabled={saving}
                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 font-medium disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                  <button
                    onClick={() => setSelectedRole(null)}
                    className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-lg border border-gray-200 p-6 text-center text-gray-500">
              <div className="text-4xl mb-4">🤖</div>
              <p>Select an agent role from the list to edit its configuration</p>
            </div>
          )}

          {/* Info Card */}
          <div className="bg-blue-50 rounded-lg border border-blue-200 p-4 mt-6">
            <h3 className="font-semibold text-blue-900 mb-2">About Agent Roles</h3>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• <strong>Director</strong> - Orchestrates the pipeline, assigns tasks to agents</li>
              <li>• <strong>PM</strong> - Creates specs, breaks down requirements</li>
              <li>• <strong>DEV</strong> - Implements features, writes code</li>
              <li>• <strong>QA</strong> - Writes and runs tests, validates functionality</li>
              <li>• <strong>Security</strong> - Reviews code for vulnerabilities</li>
              <li>• <strong>Docs</strong> - Writes documentation, updates READMEs</li>
              <li>• <strong>CI/CD</strong> - Handles deployment and integration</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
