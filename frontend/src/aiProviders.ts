const labels = {
  openai: 'OpenAI',
  anthropic: 'Claude',
  google: 'Google Gemini',
}

export function isAIProvider(
  provider: string,
): provider is keyof typeof labels {
  return Object.hasOwn(labels, provider)
}

export function aiProviderLabel(provider: string): string {
  return isAIProvider(provider) ? labels[provider] : provider
}
