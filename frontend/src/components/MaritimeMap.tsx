'use client';

import dynamic from 'next/dynamic';
import type { MaritimeMapProps } from './MaritimeMapInner';

const MaritimeMapInner = dynamic(() => import('./MaritimeMapInner'), {
  ssr: false,
  loading: () => (
    <div style={{
      height: '100%',
      width: '100%',
      minHeight: 280,
      background: 'var(--navy-950)',
      borderRadius: 8,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: 'var(--text-muted)',
      fontSize: '0.82rem',
    }}>
      Loading maritime map...
    </div>
  ),
});

export default function MaritimeMap(props: MaritimeMapProps) {
  return <MaritimeMapInner {...props} />;
}
