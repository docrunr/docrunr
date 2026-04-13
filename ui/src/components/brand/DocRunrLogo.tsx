import type { HTMLAttributes } from 'react';
import logoSvg from '../../assets/logo-black.svg?raw';

type DocRunrLogoProps = HTMLAttributes<HTMLSpanElement>;

export function DocRunrLogo({ className, style, ...rest }: DocRunrLogoProps) {
  const rootClass = ['docrunrLogo', className].filter(Boolean).join(' ');
  return (
    <span
      className={rootClass}
      style={{ lineHeight: 0, color: 'inherit', ...style }}
      dangerouslySetInnerHTML={{ __html: logoSvg }}
      {...rest}
    />
  );
}
