import { Text, Tooltip, type TextProps } from '@mantine/core';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

type EllipsisTooltipTextProps = Omit<TextProps, 'children'> & {
  /** Cell text and tooltip content when truncated */
  label: string;
};

function isTextTruncated(el: HTMLElement): boolean {
  return el.scrollWidth - el.clientWidth > 1 || el.scrollHeight - el.clientHeight > 1;
}

export function EllipsisTooltipText({ label, ...textProps }: EllipsisTooltipTextProps) {
  const ref = useRef<HTMLParagraphElement>(null);
  const [truncated, setTruncated] = useState(false);

  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) {
      setTruncated(false);
      return;
    }
    setTruncated(isTextTruncated(el));
  }, []);

  useLayoutEffect(() => {
    measure();
  }, [label, measure]);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const ro = new ResizeObserver(() => measure());
    ro.observe(el);
    return () => ro.disconnect();
  }, [measure]);

  return (
    <Tooltip
      label={label}
      disabled={!truncated || label.length === 0}
      position="top"
      transitionProps={{ duration: 0 }}
    >
      <Text ref={ref} {...textProps}>
        {label}
      </Text>
    </Tooltip>
  );
}
