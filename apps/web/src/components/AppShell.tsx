import { Camera, Clock, FolderSearch, MessageCircleQuestion, Search, Settings } from 'lucide-react';
import type { ReactNode } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

import { Routes } from '@memora/core';

import { cn } from '@/lib/utils';

const TABS = [
  { to: Routes.Search, label: 'Find', Icon: Search },
  { to: Routes.Ask, label: 'Ask', Icon: MessageCircleQuestion },
  { to: Routes.Capture, label: 'Capture', Icon: Camera },
  { to: Routes.Scan, label: 'Index', Icon: FolderSearch },
  { to: Routes.Timeline, label: 'Timeline', Icon: Clock },
  { to: Routes.Settings, label: 'Settings', Icon: Settings },
] as const;

function Tab({ to, label, Icon }: { to: string; label: string; Icon: typeof Camera }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'flex flex-1 flex-col items-center justify-center gap-1 text-[0.6875rem] ' +
            'transition-colors sm:h-11 sm:flex-none sm:flex-row sm:gap-2 sm:rounded-lg ' +
            'sm:px-3 sm:text-sm',
          isActive ? 'text-accent sm:bg-accent-soft' : 'text-ink-faint hover:text-ink-muted',
        )
      }
    >
      <Icon className="size-5 sm:size-4" aria-hidden />
      {label}
    </NavLink>
  );
}

/**
 * Mobile-first app shell. Navigation sits in a thumb-reachable bottom bar at 375px
 * and moves into the header from sm up, where capture stops being the primary action.
 */
export function AppShell({ children }: { children?: ReactNode }) {
  return (
    <div className="flex h-full flex-col bg-canvas">
      <header
        className={cn(
          'flex shrink-0 items-center justify-between gap-4 border-b border-line',
          'bg-surface/80 px-4 pt-safe backdrop-blur',
        )}
      >
        <div className="flex h-14 items-center gap-2">
          <span className="text-base font-semibold tracking-tight">Memora</span>
          <span className="hidden text-xs text-ink-faint sm:inline">
            layer one &middot; live
          </span>
        </div>
        <nav className="hidden items-center gap-1 sm:flex">
          {TABS.map((tab) => (
            <Tab key={tab.to} {...tab} />
          ))}
        </nav>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto">{children ?? <Outlet />}</main>

      <nav
        className={cn(
          'flex h-navbar shrink-0 items-stretch border-t border-line bg-surface',
          'pb-safe sm:hidden',
        )}
      >
        {TABS.map((tab) => (
          <Tab key={tab.to} {...tab} />
        ))}
      </nav>
    </div>
  );
}
