/** Build the public URL for an analysis share token.
 *
 * A Vite build can set ``VITE_PUBLIC_APP_URL`` when the browser-facing URL is
 * different from the address used while developing (for example behind a
 * reverse proxy).  Without it we deliberately derive the link from the page
 * the user is currently viewing.  Docker guides often use ``0.0.0.0`` as a
 * bind address, but that is not a usable destination in a copied link, so
 * normalize it to localhost for the local-development case.
 */
export function buildPublicShareUrl(
  token: string,
  browserOrigin: string = window.location.origin,
  configuredPublicUrl: string | undefined = import.meta.env.VITE_PUBLIC_APP_URL,
): string {
  const safeToken = encodeURIComponent(token)
  const configured = configuredPublicUrl?.trim()

  if (configured) {
    try {
      const base = new URL(configured.endsWith('/') ? configured : `${configured}/`)
      return new URL(`share/${safeToken}`, base).toString()
    } catch {
      // A malformed optional deployment setting must never prevent a share
      // link from being created.  Fall back to the browser origin below.
    }
  }

  const base = new URL(browserOrigin)
  if (base.hostname === '0.0.0.0' || base.hostname === '::' || base.hostname === '[::]') {
    base.hostname = 'localhost'
  }
  return new URL(`/share/${safeToken}`, base).toString()
}
