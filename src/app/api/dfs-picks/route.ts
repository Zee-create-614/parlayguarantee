import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'

const DFS_FILE = path.join(process.cwd(), 'engine', 'dfs_output.json')

export async function GET(request: NextRequest) {
  try {
    const raw = await fs.readFile(DFS_FILE, 'utf-8')
    const data = JSON.parse(raw)
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ error: 'No DFS lineups available yet' }, { status: 404 })
  }
}
