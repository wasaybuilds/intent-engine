/**
 * Persist the in-flight scrape across in-app navigation (Scrape ↔ History).
 *
 * Celery keeps running on the server; without this, leaving the Scrape page
 * unmounts the dashboard and the UI "forgets" the job was running.
 */

const STORAGE_KEY = "intent-engine:active-scrape";

/** Snapshot of a scrape the UI should keep polling. */
export interface ActiveScrape {
  taskId: string;
  niche: string;
  location: string;
  startedAt: number;
}

/**
 * Save the active scrape so returning to `/` can resume progress polling.
 *
 * @param scrape - Task metadata to persist
 */
export function saveActiveScrape(scrape: ActiveScrape): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(scrape));
  } catch {
    // Private mode / quota — progress resume is best-effort
  }
}

/**
 * Load a previously started scrape, if any.
 *
 * @returns Active scrape or null
 */
export function loadActiveScrape(): ActiveScrape | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ActiveScrape>;
    if (
      typeof parsed.taskId !== "string" ||
      !parsed.taskId ||
      typeof parsed.niche !== "string" ||
      typeof parsed.location !== "string"
    ) {
      return null;
    }
    return {
      taskId: parsed.taskId,
      niche: parsed.niche,
      location: parsed.location,
      startedAt:
        typeof parsed.startedAt === "number" ? parsed.startedAt : Date.now(),
    };
  } catch {
    return null;
  }
}

/**
 * Clear the persisted scrape after success, failure, or cancel.
 */
export function clearActiveScrape(): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
