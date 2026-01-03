'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

interface PipelineConfig {
  id: number
  name: string
  project_id: number
  is_active: boolean
  version: number
  created_at: string
}

export default function Dashboard() {
  const [configs, setConfigs] = useState<PipelineConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/postgrest/pipeline_configs?order=created_at.desc')
      .then(r => {
        if (!r.ok) throw new Error('Failed to fetch configs')
        return r.json()
      })
      .then(data => {
        setConfigs(data)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  return (
    <div className="p-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            Pipeline Configurations
          </h2>
          <p className="text-gray-600">
            Create and manage visual pipeline configurations for your projects.
          </p>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <Link
            href="/editor/new"
            className="p-6 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
          >
            <div className="text-blue-600 font-semibold mb-1">+ New Pipeline</div>
            <div className="text-sm text-blue-500">Create a new pipeline configuration</div>
          </Link>

          <Link
            href="/monitor"
            className="p-6 bg-green-50 border border-green-200 rounded-lg hover:bg-green-100 transition-colors"
          >
            <div className="text-green-600 font-semibold mb-1">Live Monitor</div>
            <div className="text-sm text-green-500">Watch tasks flow through pipeline</div>
          </Link>

          <Link
            href="/settings"
            className="p-6 bg-purple-50 border border-purple-200 rounded-lg hover:bg-purple-100 transition-colors"
          >
            <div className="text-purple-600 font-semibold mb-1">Settings</div>
            <div className="text-sm text-purple-500">Configure Director and agents</div>
          </Link>
        </div>

        {/* Configs List */}
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-4 py-3 border-b border-gray-200">
            <h3 className="font-semibold text-gray-900">Saved Configurations</h3>
          </div>

          {loading ? (
            <div className="p-8 text-center text-gray-500">Loading...</div>
          ) : error ? (
            <div className="p-8 text-center">
              <p className="text-gray-500 mb-2">No configurations yet</p>
              <p className="text-sm text-gray-400">
                PostgREST may not be running, or the pipeline_configs table doesn&apos;t exist yet.
              </p>
              <Link
                href="/editor/new"
                className="inline-block mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Create First Pipeline
              </Link>
            </div>
          ) : configs.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <p className="mb-2">No pipeline configurations found</p>
              <Link
                href="/editor/new"
                className="inline-block mt-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Create First Pipeline
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-gray-200">
              {configs.map((config) => (
                <li key={config.id} className="p-4 hover:bg-gray-50">
                  <Link href={`/editor/${config.id}`} className="flex justify-between items-center">
                    <div>
                      <div className="font-medium text-gray-900">{config.name}</div>
                      <div className="text-sm text-gray-500">
                        Version {config.version} • Project #{config.project_id}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {config.is_active && (
                        <span className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded">
                          Active
                        </span>
                      )}
                      <span className="text-gray-400">→</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
