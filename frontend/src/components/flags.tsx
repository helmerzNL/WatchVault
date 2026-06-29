// Inline SVG flags for the language picker. Simple, dependency-free, 24×18.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;
const base = (p: P) => ({
  width: 24, height: 18, viewBox: "0 0 24 18",
  role: "img", "aria-hidden": true, ...p,
});

export function FlagDE(p: P) {
  return (
    <svg {...base(p)}>
      <rect width="24" height="6" y="0" fill="#000" />
      <rect width="24" height="6" y="6" fill="#D00" />
      <rect width="24" height="6" y="12" fill="#FFCE00" />
    </svg>
  );
}

export function FlagGB(p: P) {
  return (
    <svg {...base(p)}>
      <rect width="24" height="18" fill="#012169" />
      <path d="M0 0l24 18M24 0L0 18" stroke="#fff" strokeWidth="3.6" />
      <path d="M0 0l24 18M24 0L0 18" stroke="#C8102E" strokeWidth="2.4"
        clipPath="url(#gbcp)" />
      <clipPath id="gbcp">
        <path d="M12 9L24 0V0H22zM12 9L24 18H22zM12 9L0 18H2zM12 9L0 0H2z" />
      </clipPath>
      <path d="M12 0v18M0 9h24" stroke="#fff" strokeWidth="6" />
      <path d="M12 0v18M0 9h24" stroke="#C8102E" strokeWidth="3.6" />
    </svg>
  );
}

export function FlagES(p: P) {
  return (
    <svg {...base(p)}>
      <rect width="24" height="18" fill="#AA151B" />
      <rect width="24" height="9" y="4.5" fill="#F1BF00" />
    </svg>
  );
}

export function FlagFR(p: P) {
  return (
    <svg {...base(p)}>
      <rect width="8" height="18" x="0" fill="#0055A4" />
      <rect width="8" height="18" x="8" fill="#fff" />
      <rect width="8" height="18" x="16" fill="#EF4135" />
    </svg>
  );
}

export function FlagIT(p: P) {
  return (
    <svg {...base(p)}>
      <rect width="8" height="18" x="0" fill="#008C45" />
      <rect width="8" height="18" x="8" fill="#fff" />
      <rect width="8" height="18" x="16" fill="#CD212A" />
    </svg>
  );
}

export function FlagNL(p: P) {
  return (
    <svg {...base(p)}>
      <rect width="24" height="6" y="0" fill="#AE1C28" />
      <rect width="24" height="6" y="6" fill="#fff" />
      <rect width="24" height="6" y="12" fill="#21468B" />
    </svg>
  );
}
