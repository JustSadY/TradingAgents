/**
 * Link and image URL policy for untrusted content.
 *
 * AI report text is model output, so every `href` and `src` derived from it
 * passes through here. Both the on-screen renderer and the printable export
 * import these, so there is one policy rather than two that can drift apart.
 */

/**
 * Returns the URL if it is safe to use as a link target, otherwise `null`.
 *
 * Allows absolute `http`/`https`, `mailto:`, root-relative and dot-relative
 * paths, and bare fragments. Everything else — notably `javascript:` and
 * `data:` — is rejected, as is any URL containing a control character, which
 * could otherwise be used to smuggle a scheme past the prefix check.
 */
export function safeLinkHref(value: string): string | null {
  const href = value.trim()
  const lower = href.toLowerCase()
  if (!href || Array.from(href).some(char => char.charCodeAt(0) < 32)) return null
  if (lower.startsWith('https://') || lower.startsWith('http://') || lower.startsWith('mailto:')) return href
  if (/^(?:\/(?!\/)|\.\.?\/|#)/.test(href)) return href
  return null
}

/**
 * Returns the URL if it is safe to use as an image source, otherwise `null`.
 *
 * Stricter than {@link safeLinkHref}: a `mailto:` address or a bare fragment is
 * a valid link but never a valid image.
 */
export function safeImageSrc(value: string): string | null {
  const src = safeLinkHref(value)
  if (!src || src.startsWith('mailto:') || src.startsWith('#')) return null
  return src
}
