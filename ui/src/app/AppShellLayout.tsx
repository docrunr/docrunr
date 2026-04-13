import { ActionIcon, AppShell, Stack, Tooltip } from '@mantine/core';
import { IconFileDescription, IconInfoCircle, IconLayoutDashboard } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AboutModal } from '../features/about/components/AboutModal';
import { DocRunrLogo } from '../components/brand/DocRunrLogo';
import { AppMainToolbar, type AppSectionId } from './app-sections';
import './App.css';

type MainNavItem = {
  id: AppSectionId;
  label: string;
  icon: typeof IconLayoutDashboard | typeof IconFileDescription;
};

type NavbarLinkProps = {
  icon: typeof IconLayoutDashboard | typeof IconFileDescription | typeof IconInfoCircle;
  label: string;
  active?: boolean;
  onClick: () => void;
};

function NavbarLink({ icon: Icon, label, active = false, onClick }: NavbarLinkProps) {
  return (
    <Tooltip label={label} position="right" transitionProps={{ duration: 0 }}>
      <ActionIcon
        variant={active ? 'light' : 'subtle'}
        color="gray"
        size={48}
        radius="md"
        aria-label={label}
        onClick={onClick}
      >
        <Icon size={20} stroke={1.8} />
      </ActionIcon>
    </Tooltip>
  );
}

type AppShellLayoutProps = {
  activeSection: AppSectionId;
  onNavigate: (section: AppSectionId) => void;
  sidebarOpened: boolean;
  onToggleSidebar: () => void;
  isDarkScheme: boolean;
  onToggleColorScheme: () => void;
  children: ReactNode;
};

export function AppShellLayout({
  activeSection,
  onNavigate,
  sidebarOpened,
  onToggleSidebar,
  isDarkScheme,
  onToggleColorScheme,
  children,
}: AppShellLayoutProps) {
  const { t } = useTranslation();
  const [aboutOpened, setAboutOpened] = useState(false);
  const mainNavItems = useMemo<MainNavItem[]>(
    () => [
      { id: 'overview', label: t('nav.overview'), icon: IconLayoutDashboard },
      { id: 'queue', label: t('nav.queue'), icon: IconFileDescription },
    ],
    [t]
  );

  return (
    <AppShell
      navbar={{
        width: 88,
        breakpoint: 'sm',
        collapsed: { mobile: true, desktop: !sidebarOpened },
      }}
      padding="md"
    >
      <AppShell.Navbar p="md" className="appNavbar">
        <AppShell.Section className="sidebarBrandSection">
          <Tooltip label={t('nav.overview')} position="right" transitionProps={{ duration: 0 }}>
            <ActionIcon
              variant={activeSection === 'overview' ? 'light' : 'subtle'}
              color="gray"
              size={48}
              radius="md"
              aria-label={t('nav.overview')}
              onClick={() => onNavigate('overview')}
            >
              <DocRunrLogo className="sidebarBrandImage" />
            </ActionIcon>
          </Tooltip>
        </AppShell.Section>

        <AppShell.Section grow>
          <Stack gap="sm" align="center" className="sidebarNavStack">
            {mainNavItems.map((item) => (
              <NavbarLink
                key={item.id}
                icon={item.icon}
                label={item.label}
                active={item.id === activeSection}
                onClick={() => onNavigate(item.id)}
              />
            ))}
          </Stack>
        </AppShell.Section>

        <AppShell.Section>
          <Stack gap="sm" align="center" className="sidebarFooterStack">
            <NavbarLink
              icon={IconInfoCircle}
              label={t('nav.about')}
              active={aboutOpened}
              onClick={() => setAboutOpened(true)}
            />
            <AboutModal opened={aboutOpened} onClose={() => setAboutOpened(false)} />
          </Stack>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Stack gap="xl" mih="calc(100vh - calc(var(--mantine-spacing-md) * 2))">
          <AppMainToolbar
            sidebarOpened={sidebarOpened}
            onToggleSidebar={onToggleSidebar}
            isDarkScheme={isDarkScheme}
            onToggleColorScheme={onToggleColorScheme}
          />
          {children}
        </Stack>
      </AppShell.Main>
    </AppShell>
  );
}
