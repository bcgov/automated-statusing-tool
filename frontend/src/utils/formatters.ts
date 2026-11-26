
/**
 * Formats an ISO datetime string into a readable local date and time.
 */
export const formatDateTime = (dateTime: string): string => {
  const date = new Date(dateTime);

  if (Number.isNaN(date.getTime())) return "Invalid date";

  return date.toLocaleString("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

/**
 * Rounds a number to two decimal places.
 */
export const roundToTwo = (value: number | null): string => {
  if (value === null || !Number.isFinite(value)) return "N/A";

  return value.toFixed(2);
};

/**
 * Format strings to sentence case
 */
export const toSentenceCase = (text: string): string => {
  if (!text) return "";

  const normalized = text.trim().toLowerCase();

  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};
