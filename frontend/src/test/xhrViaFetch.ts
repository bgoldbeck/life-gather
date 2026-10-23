// Photo uploads use XMLHttpRequest for progress (src/photoUpload.ts). In tests,
// route it through the global fetch so a test stubs every request one way.
// It forwards method, URL, headers, body and an abort signal, reports upload
// progress at 50% before the request and 100% once it is sent, and keeps
// fetch's rejection (a lost response) apart from an HTTP status.

type Listener = ((event: ProgressEvent) => void) | null

export class XHRViaFetch {
  status = 0
  responseText = ''
  withCredentials = false
  upload: { onprogress: Listener } = { onprogress: null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  ontimeout: (() => void) | null = null
  onabort: (() => void) | null = null
  private method = 'GET'
  private url = ''
  private headers: Record<string, string> = {}
  private controller = new AbortController()

  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value
  }
  abort() {
    if (this.controller.signal.aborted) return
    this.controller.abort()
    this.onabort?.()
  }
  send(body?: BodyInit | null) {
    const progress = (loaded: number) =>
      this.upload.onprogress?.({
        lengthComputable: true,
        loaded,
        total: 100,
      } as ProgressEvent)
    progress(50)
    const signal = this.controller.signal
    void fetch(this.url, {
      method: this.method,
      headers: this.headers,
      body,
      signal,
    }).then(
      async (response) => {
        if (signal.aborted) return
        progress(100)
        this.status = response.status
        this.responseText = await response.text()
        if (!signal.aborted) this.onload?.()
      },
      () => {
        if (!signal.aborted) this.onerror?.()
      },
    )
  }
}
