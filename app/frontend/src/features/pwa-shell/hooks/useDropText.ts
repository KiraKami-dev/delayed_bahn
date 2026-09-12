import { useCallback, useState, type DragEvent } from "react"

/** Drag-and-drop of plain text or a .txt file onto an element. */
export function useDropText(onText: (text: string) => void) {
  const [over, setOver] = useState(false)
  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault()
    setOver(true)
  }, [])
  const onDragLeave = useCallback(() => setOver(false), [])
  const onDrop = useCallback(
    async (e: DragEvent) => {
      e.preventDefault()
      setOver(false)
      const dt = e.dataTransfer
      const file = dt.files?.[0]
      if (file && (file.type.startsWith("text/") || file.name.endsWith(".txt"))) {
        onText(await file.text())
        return
      }
      const text = dt.getData("text/plain") || dt.getData("text/uri-list")
      if (text) onText(text)
    },
    [onText],
  )
  return { over, handlers: { onDragOver, onDragLeave, onDrop } }
}
