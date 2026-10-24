import { useId, useState, type InputHTMLAttributes } from 'react'
import { Eye, EyeOff } from 'lucide-react'

type PasswordInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'type'
> & {
  revealLabel?: string
}

export function PasswordInput({
  revealLabel = 'Show password',
  id,
  className,
  disabled,
  ...inputProps
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false)
  const generatedId = useId()
  const inputId = id ?? generatedId
  const Icon = visible ? EyeOff : Eye

  return (
    <span className="password-input">
      <input
        {...inputProps}
        id={inputId}
        type={visible ? 'text' : 'password'}
        className={['password-input-field', className]
          .filter(Boolean)
          .join(' ')}
        disabled={disabled}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
      />
      <button
        type="button"
        className="password-input-toggle"
        aria-label={revealLabel}
        aria-pressed={visible}
        aria-controls={inputId}
        title={visible ? revealLabel.replace(/^Show/, 'Hide') : revealLabel}
        disabled={disabled}
        // Keep focus (and the phone keyboard) on the field while toggling.
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => setVisible((shown) => !shown)}
      >
        <Icon aria-hidden="true" size={18} />
      </button>
    </span>
  )
}
