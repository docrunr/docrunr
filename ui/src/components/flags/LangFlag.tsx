import { Box, useComputedColorScheme } from '@mantine/core';
import gbFlagUrl from '../../assets/flags/gb.svg?url';
import nlFlagUrl from '../../assets/flags/nl.svg?url';
import type { UiLanguage } from '../../i18n';

function flagUrlForLanguage(code: UiLanguage): string {
  switch (code) {
    case 'en':
      return gbFlagUrl;
    case 'nl':
      return nlFlagUrl;
  }
}

type LangFlagProps = {
  code: UiLanguage;
  /** CSS height in px; width follows 3:2 ratio */
  height?: number;
};

export function LangFlag({ code, height = 14 }: LangFlagProps) {
  const colorScheme = useComputedColorScheme('light');
  const src = flagUrlForLanguage(code);
  const width = Math.round((height * 3) / 2);

  return (
    <Box
      aria-hidden
      style={{
        width,
        height,
        borderRadius: 1,
        overflow: 'hidden',
        flexShrink: 0,
        boxShadow:
          colorScheme === 'dark'
            ? '0 1px 2px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.06)'
            : '0 1px 2px rgba(0,0,0,0.12)',
      }}
    >
      <img
        src={src}
        alt=""
        width={width}
        height={height}
        draggable={false}
        style={{
          display: 'block',
          width: '100%',
          height: '100%',
          objectFit: 'cover',
        }}
      />
    </Box>
  );
}
