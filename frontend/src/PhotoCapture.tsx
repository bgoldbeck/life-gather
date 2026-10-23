import type { Ref } from 'react'
import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { PHOTO_ACCEPT } from './photoUpload'
import './photoCapture.css'

// Opens the phone's rear camera through the ordinary file input; no custom
// camera code. Shown on touch screens only (photoCapture.css), since desktop
// browsers ignore `capture` and would just open a second file picker.
export function CameraCaptureButton({
  label,
  disabled,
  inputRef,
  onCapture,
}: {
  label: string
  disabled: boolean
  inputRef?: Ref<HTMLInputElement>
  onCapture: (file: File) => void
}) {
  return (
    <label
      className={cn(
        buttonVariants({ variant: 'default' }),
        'camera-capture',
        disabled && 'pointer-events-none opacity-50',
      )}
    >
      {label}
      <input
        ref={inputRef}
        className="camera-capture-input"
        type="file"
        accept={PHOTO_ACCEPT}
        capture="environment"
        disabled={disabled}
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (file) onCapture(file)
        }}
      />
    </label>
  )
}

export function PhotoUploadProgress({
  percent,
  onCancel,
}: {
  percent: number
  onCancel: () => void
}) {
  return (
    <div className="photo-upload-progress">
      <progress max={100} value={percent} aria-label="Photo upload progress">
        {percent}%
      </progress>
      <span aria-hidden="true">{percent}%</span>
      <Button type="button" variant="outline" onClick={onCancel}>
        Cancel upload
      </Button>
    </div>
  )
}

export const CANCELLED_MESSAGE =
  'Upload cancelled. If it had already reached your server, it is in Photos; sending the same photo again never makes a copy.'
