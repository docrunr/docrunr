import type { AppSectionId } from './app-sections';

export function normalizePathname(pathname: string): string {
  if (!pathname || pathname === '/') {
    return '/';
  }
  const trimmed = pathname.replace(/\/+$/, '');
  return trimmed === '' ? '/' : trimmed;
}

export function isKnownAppPath(pathname: string): boolean {
  const p = normalizePathname(pathname);
  return p === '/' || p === '/queue';
}

export function sectionFromPathname(pathname: string): AppSectionId {
  const p = normalizePathname(pathname);
  if (p === '/queue') return 'queue';
  return 'overview';
}

export function pathFromSection(section: AppSectionId): string {
  switch (section) {
    case 'queue':
      return '/queue';
    default:
      return '/';
  }
}

const SIDEBAR_KEY = 'docrunr.sidebar.opened';

export function readStoredSidebarOpened(): boolean {
  if (typeof localStorage === 'undefined') {
    return false;
  }
  try {
    const raw = localStorage.getItem(SIDEBAR_KEY);
    if (raw === 'true') return true;
    if (raw === 'false') return false;
    return false;
  } catch {
    return false;
  }
}

export function writeStoredSidebarOpened(opened: boolean): void {
  try {
    localStorage.setItem(SIDEBAR_KEY, opened ? 'true' : 'false');
  } catch {
    // ignore quota / private mode
  }
}
