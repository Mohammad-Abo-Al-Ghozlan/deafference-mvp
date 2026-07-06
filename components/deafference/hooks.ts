"use client"

import { useCallback, useEffect, useRef } from "react"

export function useInterval(callback: () => void, delay: number | null) {
  const savedCallback = useRef(callback)

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    if (delay === null) return
    const id = setInterval(() => savedCallback.current(), delay)
    return () => clearInterval(id)
  }, [delay])
}

export function useStableCallback<T extends (...args: any[]) => any>(callback: T) {
  const ref = useRef(callback)
  useEffect(() => {
    ref.current = callback
  }, [callback])
  return useCallback((...args: Parameters<T>) => ref.current(...args), [])
}
