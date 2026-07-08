/**
 * SSE 流式读取 composable
 * 用法: for await (const data of streamSSE('/api/novels/xxx/write/1', { feedback: '' })) { ... }
 */
export async function* streamSSE(url, body = {}) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const err = await response.text()
    throw new Error(`API 错误 ${response.status}: ${err}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n\n')
    buffer = lines.pop()

    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('data: ')) {
        try {
          yield JSON.parse(trimmed.slice(6))
        } catch {
          // 非 JSON 行（如注释或空数据）跳过
        }
      }
    }
  }
}

/**
 * 简单 fetch 封装
 */
export async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API 错误 ${res.status}: ${err}`)
  }
  return res.json()
}
