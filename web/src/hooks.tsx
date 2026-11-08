import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { get } from './api'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, XCircle, Info } from 'lucide-react'

export function useApi<T>(path: string | null, intervalMs = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const alive = useRef(true)
  const load = useCallback(async () => {
    if (!path) return
    try {
      const d = await get<T>(path)
      if (alive.current) { setData(d); setError(null) }
    } catch (e) {
      if (alive.current) setError((e as Error).message)
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [path])
  useEffect(() => {
    alive.current = true
    setLoading(true)
    void load()
    const t = intervalMs > 0 ? setInterval(() => void load(), intervalMs) : undefined
    return () => { alive.current = false; if (t) clearInterval(t) }
  }, [load, intervalMs])
  return { data, error, loading, reload: load }
}

type ToastKind = 'ok' | 'bad' | 'info'
interface ToastItem { id: number; kind: ToastKind; text: string }
const ToastCtx = createContext<(kind: ToastKind, text: string) => void>(() => undefined)
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const push = useCallback((kind: ToastKind, text: string) => {
    const id = Date.now() + Math.random()
    setItems((s) => [...s, { id, kind, text }])
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), 4200)
  }, [])
  const icon = { ok: <CheckCircle2 size={18} color="var(--ok)" />, bad: <XCircle size={18} color="var(--bad)" />, info: <Info size={18} color="var(--info)" /> }
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-wrap">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div key={t.id} className="toast" initial={{ opacity: 0, x: 40, scale: 0.96 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: 40 }}>
              {icon[t.kind]}<div>{t.text}</div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  )
}
