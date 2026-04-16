import { Center, Loader, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { WorkerModeProvider } from '../contexts/WorkerModeContext';
import { useWorkerMode } from '../contexts/useWorkerMode';
import { usePolling } from '../hooks/usePolling';
import { fetchJobs, fetchOverview } from '../services/workerApi';
import type { AnyJobsResponse } from '../services/workerApi.types';
import { AppSectionContent, type AppSectionId } from './app-sections';
import { AppShellLayout } from './AppShellLayout';
import { LoginScreen } from './LoginScreen';
import { WorkerAuthProvider } from './WorkerAuthContext';
import { useWorkerAuth } from './useWorkerAuth';
import {
  isKnownAppPath,
  normalizePathname,
  pathFromSection,
  readStoredSidebarOpened,
  sectionFromPathname,
  writeStoredSidebarOpened,
} from './url-section';

function initialPathname(): string {
  if (typeof window === 'undefined') {
    return '/';
  }
  const raw = window.location.pathname;
  if (!isKnownAppPath(raw)) {
    return '/';
  }
  return normalizePathname(raw);
}

const emptyJobs: AnyJobsResponse = {
  items: [],
  count: 0,
  total: 0,
  limit: 500,
};

function AppBody() {
  const [pathname, setPathname] = useState(initialPathname);
  const [desktopSidebarOpened, setDesktopSidebarOpened] = useState(readStoredSidebarOpened);
  const [jobs, setJobs] = useState<AnyJobsResponse>({
    items: [],
    count: 0,
    total: 0,
    limit: 100,
  });
  const [queueStatusFilter, setQueueStatusFilter] = useState<'' | 'ok' | 'error' | 'processing'>(
    ''
  );
  const [queueSearch, setQueueSearch] = useState('');
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [queueRabbitmq, setQueueRabbitmq] = useState<string | null>(null);
  const { setColorScheme } = useMantineColorScheme();
  const computedColorScheme = useComputedColorScheme('light');
  const isNarrowViewport = useMediaQuery('(max-width: 48em)') ?? false;
  const { status, authEnabled, authenticated, canFetchProtected } = useWorkerAuth();
  const { mode } = useWorkerMode();

  useEffect(() => {
    if (!canFetchProtected) {
      setJobs(emptyJobs);
      setQueueError(null);
      setQueueRabbitmq(null);
    }
  }, [canFetchProtected]);

  const activeSection = useMemo(() => sectionFromPathname(pathname), [pathname]);
  const sidebarOpened = isNarrowViewport ? false : desktopSidebarOpened;

  useLayoutEffect(() => {
    if (!isKnownAppPath(window.location.pathname)) {
      history.replaceState(null, '', '/');
    }
  }, []);

  useEffect(() => {
    const onPopState = () => {
      const raw = window.location.pathname;
      if (!isKnownAppPath(raw)) {
        history.replaceState(null, '', '/');
        setPathname('/');
        return;
      }
      setPathname(normalizePathname(raw));
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const onNavigate = useCallback((section: AppSectionId) => {
    const next = pathFromSection(section);
    const normalized = normalizePathname(next);
    if (normalizePathname(window.location.pathname) !== normalized) {
      history.pushState(null, '', next);
    }
    setPathname(normalized);
  }, []);

  const onToggleSidebar = useCallback(() => {
    if (isNarrowViewport) {
      return;
    }
    setDesktopSidebarOpened((prev) => {
      const next = !prev;
      writeStoredSidebarOpened(next);
      return next;
    });
  }, [isNarrowViewport]);

  usePolling(
    activeSection === 'queue',
    async (isMounted) => {
      try {
        setQueueLoading(true);
        const jobsPromise = canFetchProtected
          ? fetchJobs(
              {
                limit: 500,
                status: queueStatusFilter,
                search: queueSearch,
              },
              mode
            )
          : Promise.resolve(emptyJobs);
        const [jobsOutcome, overviewOutcome] = await Promise.allSettled([
          jobsPromise,
          fetchOverview(mode),
        ]);
        if (!isMounted()) return;

        if (jobsOutcome.status === 'fulfilled') {
          setJobs(jobsOutcome.value);
          setQueueError(null);
        } else {
          const reason = jobsOutcome.reason;
          setQueueError(reason instanceof Error ? reason.message : 'Unknown request failure');
        }

        if (overviewOutcome.status === 'fulfilled') {
          setQueueRabbitmq(overviewOutcome.value.health.rabbitmq);
        }
      } finally {
        if (isMounted()) {
          setQueueLoading(false);
        }
      }
    },
    [activeSection, canFetchProtected, queueSearch, queueStatusFilter, mode]
  );

  if (status === 'loading') {
    return (
      <Center mih="100vh">
        <Loader />
      </Center>
    );
  }

  if (authEnabled && !authenticated) {
    return <LoginScreen />;
  }

  return (
    <AppShellLayout
      activeSection={activeSection}
      onNavigate={onNavigate}
      sidebarOpened={sidebarOpened}
      onToggleSidebar={onToggleSidebar}
      isDarkScheme={computedColorScheme === 'dark'}
      onToggleColorScheme={() => setColorScheme(computedColorScheme === 'dark' ? 'light' : 'dark')}
    >
      <AppSectionContent
        activeSection={activeSection}
        jobs={jobs}
        queueLoading={queueLoading}
        queueError={queueError}
        queueRabbitmq={queueRabbitmq}
        queueSearch={queueSearch}
        onQueueSearchChange={setQueueSearch}
        queueStatusFilter={queueStatusFilter}
        onQueueStatusFilterChange={setQueueStatusFilter}
      />
    </AppShellLayout>
  );
}

export default function App() {
  return (
    <WorkerModeProvider>
      <WorkerAuthProvider>
        <AppBody />
      </WorkerAuthProvider>
    </WorkerModeProvider>
  );
}
