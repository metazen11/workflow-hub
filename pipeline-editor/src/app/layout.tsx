import type { Metadata } from 'next'
import '@/styles/globals.css'
import { AppShell } from '@/components/layout/AppShell'

export const metadata: Metadata = {
  title: 'Pipeline Editor - Agentic Workflow Hub',
  description: 'Visual pipeline editor for configuring and monitoring agentic workflows',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  )
}
