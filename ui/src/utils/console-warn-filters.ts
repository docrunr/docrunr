/**
 * Some chart libraries warn when a responsive chart mounts before its container has a
 * stable size (common in flex/grid). Those messages are noisy and usually harmless.
 * Only messages matching the known pattern are dropped; everything else still logs.
 */
let filtersInstalled = false;

function isSuppressedChartSizeWarning(text: string): boolean {
  return (
    text.includes('of chart should be greater than 0') &&
    text.includes('please check the style of container')
  );
}

function warnArgsToText(args: unknown[]): string {
  return args
    .map((a) => {
      if (typeof a === 'string') return a;
      if (typeof a === 'number' || typeof a === 'boolean') return String(a);
      if (a instanceof Error) return a.message;
      return '';
    })
    .join(' ');
}

if (!filtersInstalled && typeof console !== 'undefined') {
  filtersInstalled = true;
  const originalWarn = console.warn.bind(console);
  console.warn = (...args: unknown[]) => {
    if (isSuppressedChartSizeWarning(warnArgsToText(args))) {
      return;
    }
    originalWarn(...args);
  };
}

export {};
