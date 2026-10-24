import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { PasswordInput } from './PasswordInput'

describe('PasswordInput', () => {
  it('reveals and hides the typed password', async () => {
    const user = userEvent.setup()
    render(
      <label>
        Password
        <PasswordInput defaultValue="" />
      </label>,
    )
    const field = screen.getByLabelText('Password')
    const toggle = screen.getByRole('button', { name: 'Show password' })
    expect(field).toHaveAttribute('type', 'password')
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    expect(toggle).toHaveAttribute('aria-controls', field.id)

    await user.type(field, 'correct horse')
    await user.click(toggle)
    expect(field).toHaveAttribute('type', 'text')
    expect(field).toHaveValue('correct horse')
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    expect(toggle).toHaveAttribute('title', 'Hide password')

    await user.click(toggle)
    expect(field).toHaveAttribute('type', 'password')
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
  })

  it('does not submit the form and follows the field disabled state', async () => {
    const user = userEvent.setup()
    let submitted = false
    const { rerender } = render(
      <form onSubmit={() => (submitted = true)}>
        <PasswordInput aria-label="Password" />
      </form>,
    )
    await user.click(screen.getByRole('button', { name: 'Show password' }))
    expect(submitted).toBe(false)
    rerender(
      <form>
        <PasswordInput aria-label="Password" disabled />
      </form>,
    )
    expect(screen.getByRole('button', { name: 'Show password' })).toBeDisabled()
  })
})
