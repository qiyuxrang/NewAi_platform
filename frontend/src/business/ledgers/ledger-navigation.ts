let boundaryInstalled = false
let activePop: ((event: PopStateEvent) => void) | null = null

// Install before BrowserRouter: native Window events follow registration order, even with capture=true.
export function installLedgerBrowserBoundary(target: Window): void {
  if (boundaryInstalled) return
  target.addEventListener('popstate', event => activePop?.(event))
  boundaryInstalled = true
}

export function installLedgerNavigationGuard(target: Window, canLeave: () => boolean): () => void {
  let previous = { href: target.location.href, state: target.history.state }
  let approved = false
  const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
  const guard = (event: Event) => {
    if (!canLeave()) event.preventDefault()
    else { approved = true; queueMicrotask(() => { approved = false }) }
  }
  const pop = (event: PopStateEvent) => {
    const current = { href: target.location.href, state: target.history.state }
    if (current.href === previous.href || approved || canLeave()) { previous = current; return }
    // popstate is after traversal. The early boundary blocks router listeners before they can unmount this page.
    event.stopImmediatePropagation()
    const from = previous.state?.idx, to = current.state?.idx
    if (Number.isInteger(from) && Number.isInteger(to) && from !== to) target.history.go(from - to)
    else target.history.replaceState(previous.state, '', previous.href)
  }
  activePop = pop
  target.addEventListener('beforeunload', unload)
  target.addEventListener('portal:navigation-guard', guard)
  return () => {
    if (activePop === pop) activePop = null
    target.removeEventListener('beforeunload', unload)
    target.removeEventListener('portal:navigation-guard', guard)
  }
}
