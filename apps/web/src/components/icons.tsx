import type { SVGProps } from "react";

type IconName =
  | "logo"
  | "message-square"
  | "folder-open"
  | "database"
  | "bot"
  | "shield"
  | "user"
  | "search"
  | "plus"
  | "chevron-right"
  | "chevron-down"
  | "chevron-left"
  | "trash"
  | "copy"
  | "refresh"
  | "arrow-up"
  | "arrow-down"
  | "settings"
  | "grid"
  | "home"
  | "users"
  | "key"
  | "moon"
  | "sun"
  | "monitor"
  | "check"
  | "alert-circle"
  | "info"
  | "external-link"
  | "download"
  | "slash"
  | "hash"
  | "at"
  | "paperclip"
  | "sliders"
  | "more";

const PATHS: Record<IconName, string | string[]> = {
  logo: ["M12 2L2 7l10 5 10-5-10-5z", "M2 17l10 5 10-5", "M2 12l10 5 10-5"],
  "message-square": "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  "folder-open": ["M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h6l2 3h8a2 2 0 0 1 2 2z"],
  database: ["M4 6c0 1.7 4 3 8 3s8-1.3 8-3-4-3-8-3-8 1.3-8 3z", "M4 12c0 1.7 4 3 8 3s8-1.3 8-3", "M4 18c0 1.7 4 3 8 3s8-1.3 8-3"],
  bot: ["M9 2h6l1 3h3a2 2 0 0 1 2 2v9a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5V7a2 2 0 0 1 2-2h3z", "M9 11h.01", "M15 11h.01", "M8 15c1 .8 2.3 1.2 4 1.2s3-.4 4-1.2"],
  shield: ["M12 2l7 4v5c0 5-3.4 9.7-7 11-3.6-1.3-7-6-7-11V6z"],
  user: ["M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4z", "M4 21v-1a6 6 0 0 1 12 0v1"],
  search: ["M21 21l-4.35-4.35", "M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"],
  plus: "M12 5v14M5 12h14",
  "chevron-right": "M9 18l6-6-6-6",
  "chevron-down": "M6 9l6 6 6-6",
  "chevron-left": "M15 18l-6-6 6-6",
  trash: ["M3 6h18", "M19 6l-1 14H6L5 6", "M8 6V4h8v2"],
  copy: ["M9 9h13v13H9z", "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"],
  refresh: ["M21 12a9 9 0 1 1-3-6.7", "M21 3v6h-6"],
  "arrow-up": "M12 19V5M5 12l7-7 7 7",
  "arrow-down": "M12 5v14M5 12l7 7 7-7",
  settings: ["M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"],
  grid: ["M4 4h7v7H4z", "M13 4h7v7h-7z", "M4 13h7v7H4z", "M13 13h7v7h-7z"],
  home: ["M3 11l9-8 9 8", "M5 10v10h14V10"],
  users: ["M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M13 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8", "M22 21v-2a4 4 0 0 0-3-3.87"],
  key: ["M21 2l-8 8", "M15 8l1.5 1.5", "M7.5 14.5a5 5 0 1 1 7 7 5 5 0 0 1-7-7z"],
  moon: ["M21 12.8A8.2 8.2 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"],
  sun: ["M12 4V2", "M12 22v-2", "M5 5l1.4 1.4", "M17.6 17.6L19 19", "M4 12H2", "M22 12h-2", "M5 19l1.4-1.4", "M17.6 6.4L19 5", "M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8z"],
  monitor: ["M4 5h16v11H4z", "M8 20h8", "M12 16v4"],
  check: "M20 6 9 17l-5-5",
  "alert-circle": ["M12 9v4", "M12 17h.01", "M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20z"],
  info: ["M12 16v-4", "M12 8h.01", "M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20z"],
  "external-link": ["M14 3h7v7", "M10 14 21 3", "M21 14v7h-7", "M3 10v11h11"],
  download: ["M12 3v12", "M7 10l5 5 5-5", "M5 21h14"],
  slash: ["M18 6 6 18"],
  hash: ["M4 9h16", "M3 15h16", "M10 3 8 21", "M16 3l-2 18"],
  at: ["M15.5 8.5a4 4 0 1 0 0 7.8", "M19 12v1.5a5.5 5.5 0 1 1-2.5-4.6"],
  paperclip: ["M21.4 11.1 12 20.5a6 6 0 0 1-8.5-8.5l9.4-9.4a4 4 0 1 1 5.7 5.7l-9.5 9.5a2 2 0 0 1-2.8-2.8l8.8-8.8"],
  sliders: ["M4 6h10", "M18 6h2", "M8 12h12", "M4 12h2", "M14 18h6", "M4 18h8"],
  more: ["M5 12h.01", "M12 12h.01", "M19 12h.01"],
};

export function Icon({
  name,
  className,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName }) {
  const path = PATHS[name];
  const paths = Array.isArray(path) ? path : [path];

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
