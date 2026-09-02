'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Satellite,
  Ship,
  Search,
  BarChart3,
  Database,
  Activity,
  Radio,
} from 'lucide-react';

const navItems = [
  { href: '/', label: 'Overview', icon: LayoutDashboard },
  { href: '/detection', label: 'Oil Spill Detection', icon: Satellite },
  { href: '/vessels', label: 'AIS Vessel Analysis', icon: Ship },
  { href: '/investigations', label: 'Investigations', icon: Search },
  { href: '/analytics', label: 'AIS Analytics', icon: BarChart3 },
  { href: '/explorer', label: 'Data Explorer', icon: Database },
  { href: '/pipeline', label: 'Pipeline Status', icon: Activity },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div style={{
        padding: '20px 16px 24px',
        borderBottom: '1px solid var(--border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: 32, height: 32,
            borderRadius: 8,
            background: 'linear-gradient(135deg, #06b6d4, #3b82f6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Radio size={18} color="white" />
          </div>
          <div>
            <div className="nav-label" style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>
              SENTINEL
            </div>
            <div className="nav-label" style={{ fontSize: '0.62rem', fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              Maritime Intelligence
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ padding: '12px 8px', flex: 1 }}>
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '9px 12px',
                marginBottom: '2px',
                borderRadius: '8px',
                fontSize: '0.82rem',
                fontWeight: isActive ? 600 : 400,
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                background: isActive ? 'rgba(34, 211, 238, 0.08)' : 'transparent',
                textDecoration: 'none',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'rgba(148, 163, 184, 0.06)';
                  e.currentTarget.style.color = 'var(--text-primary)';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = 'var(--text-secondary)';
                }
              }}
            >
              <Icon size={18} style={{ flexShrink: 0 }} />
              <span className="nav-label">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* System status footer */}
      <div className="nav-label" style={{
        padding: '12px 16px',
        borderTop: '1px solid var(--border)',
        fontSize: '0.68rem',
        color: 'var(--text-muted)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green-400)' }} />
          System Online
        </div>
        <div style={{ opacity: 0.7 }}>Oil Spill Detection v1.0</div>
      </div>
    </aside>
  );
}
