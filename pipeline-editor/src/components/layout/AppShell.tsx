import React from 'react'

type AppShellProps = {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex flex-col min-h-screen">
      <header className="h-14 border-b border-gray-200 bg-white px-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold text-gray-900">
            Pipeline Editor
          </h1>
          <span className="text-sm text-gray-500">v2.5</span>
        </div>
        <nav className="flex items-center gap-4">
          <a href="/" className="text-sm text-gray-600 hover:text-gray-900">
            Dashboard
          </a>
          <a href="/editor" className="text-sm text-gray-600 hover:text-gray-900">
            Editor
          </a>
          <a href="/monitor" className="text-sm text-gray-600 hover:text-gray-900">
            Monitor
          </a>
          <a href="/settings" className="text-sm text-gray-600 hover:text-gray-900">
            Settings
          </a>
          <a
            href="http://localhost:8000/ui/"
            target="_blank"
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            Back to Hub →
          </a>
        </nav>
      </header>
      <main className="flex-1">
        {children}
      </main>
    </div>
  )
}
