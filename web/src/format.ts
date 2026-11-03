const LABELS: Record<string, string> = {
  direct_message_notification: "Direct message notification",
  direct_email: "Direct email",
  platform_activity: "Platform activity",
  automated_notification: "Automated notification",
  unclassified_email: "Unclassified email",
  review: "Review candidate",
  reply: "Needs reply",
  waiting: "Waiting",
  follow_up: "Follow up",
  open: "Open",
  snoozed: "Snoozed",
  done: "Done",
  dismissed: "Dismissed",
  active: "Active",
  withdrawn: "Withdrawn",
  unmatched: "Unresolved",
  verified: "Linked",
  manual: "manual link",
  parser: "parser observed",
  email: "email",
  linkedin: "LinkedIn",
  reddit: "Reddit",
  x: "X",
  instagram: "Instagram",
  xiaohongshu: "Xiaohongshu",
  unknown: "unknown platform",
};

export function humanize(value: string | null | undefined): string {
  if (!value) return "Unknown";
  return LABELS[value] ?? value.replaceAll("_", " ");
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Time unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time unknown";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
}
