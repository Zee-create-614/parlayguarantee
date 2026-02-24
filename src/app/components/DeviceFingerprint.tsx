'use client'

import { useEffect, useRef } from 'react'

// Simple hash function (djb2 variant)
function hashString(str: string): string {
  let hash = 5381
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) & 0xffffffff
  }
  // Convert to hex and pad
  return (hash >>> 0).toString(16).padStart(8, '0')
}

function getCanvasFingerprint(): string {
  try {
    const canvas = document.createElement('canvas')
    canvas.width = 200
    canvas.height = 50
    const ctx = canvas.getContext('2d')
    if (!ctx) return 'no-canvas'
    
    ctx.textBaseline = 'top'
    ctx.font = '14px Arial'
    ctx.fillStyle = '#f60'
    ctx.fillRect(125, 1, 62, 20)
    ctx.fillStyle = '#069'
    ctx.fillText('ParlayGuarantee', 2, 15)
    ctx.fillStyle = 'rgba(102, 204, 0, 0.7)'
    ctx.fillText('fingerprint', 4, 35)
    
    return canvas.toDataURL()
  } catch {
    return 'canvas-error'
  }
}

function getWebGLRenderer(): string {
  try {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl') as WebGLRenderingContext | null
    if (!gl) return 'no-webgl'
    const debugInfo = (gl as WebGLRenderingContext).getExtension('WEBGL_debug_renderer_info')
    if (!debugInfo) return 'no-debug-info'
    return (gl as WebGLRenderingContext).getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || 'unknown'
  } catch {
    return 'webgl-error'
  }
}

export function generateFingerprint(): string {
  const components = [
    `${screen.width}x${screen.height}x${screen.colorDepth}`,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
    navigator.language,
    navigator.platform,
    navigator.hardwareConcurrency?.toString() || 'unknown',
    getCanvasFingerprint(),
    getWebGLRenderer(),
    (navigator as any).deviceMemory?.toString() || 'unknown',
    new Date().getTimezoneOffset().toString(),
  ]
  
  const raw = components.join('|||')
  // Double hash for more entropy
  const h1 = hashString(raw)
  const h2 = hashString(raw.split('').reverse().join(''))
  const h3 = hashString(raw + raw)
  const h4 = hashString(h1 + h2)
  
  return `${h1}${h2}${h3}${h4}`
}

// Store in cookie
function setCookie(name: string, value: string, days: number) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString()
  document.cookie = `${name}=${value}; expires=${expires}; path=/; SameSite=Lax`
}

export function getStoredFingerprint(): string | null {
  const match = document.cookie.match(new RegExp('(?:^|; )pg_dfp=([^;]*)'))
  return match ? match[1] : null
}

interface DeviceFingerprintProps {
  onFingerprint?: (fp: string) => void
}

export default function DeviceFingerprint({ onFingerprint }: DeviceFingerprintProps) {
  const generated = useRef(false)

  useEffect(() => {
    if (generated.current) return
    generated.current = true

    // Check cookie first
    let fp = getStoredFingerprint()
    if (!fp) {
      fp = generateFingerprint()
      setCookie('pg_dfp', fp, 365)
    }
    
    onFingerprint?.(fp)
  }, [onFingerprint])

  return null // Invisible component
}
