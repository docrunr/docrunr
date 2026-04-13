export function SidebarToggleIcon({ opened }: { opened: boolean }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect
        x="2.25"
        y="3.25"
        width="15.5"
        height="13.5"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <rect
        x="3.5"
        y="4.5"
        width="4.5"
        height="11"
        rx="1"
        fill="currentColor"
        fillOpacity={opened ? 0.18 : 0.12}
      />
      <path d="M8.75 4V16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
