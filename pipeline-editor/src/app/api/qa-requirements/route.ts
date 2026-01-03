import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

export async function GET() {
  const templatePath = path.resolve(process.cwd(), '..', 'config', 'qa_requirements.json')
  try {
    const raw = await fs.promises.readFile(templatePath, 'utf-8')
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return NextResponse.json([])
    }
    return NextResponse.json(parsed)
  } catch (err) {
    return NextResponse.json([])
  }
}
