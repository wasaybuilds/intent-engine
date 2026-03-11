import type {
  ScrapeHistoryResponse,
  ScrapeJobDetailResponse,
  TaskStatusResponse,
  TaskSubmitResponse,
  WebhookConfigureResponse,
  WebhookStatusResponse,
} from "@/types/lead";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;

/**
 * Build request headers with optional Clerk JWT.
 *
 * @param token - Clerk session token
 * @param json - Include Content-Type application/json
 */
function buildHeaders(
  token?: string | null,
  json = false,
): HeadersInit {
  const headers: Record<string, string> = {};
  if (json) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

/**
 * Parse API error responses into a user-facing message.
 *
 * @param response - Failed fetch response
 */
async function parseError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => ({}));
  if (typeof body.detail === "string") return body.detail;
  return fallback;
}

/**
 * Enqueue a scrape job and return the Celery task id immediately.
 *
 * @param niche - Target business niche
 * @param location - Geographic search area
 * @param token - Clerk JWT
 */
export async function enqueueScrape(
  niche: string,
  location: string,
  token?: string | null,
): Promise<TaskSubmitResponse> {
  const response = await fetch(`${API_BASE}/api/scrape`, {
    method: "POST",
    headers: buildHeaders(token, true),
    body: JSON.stringify({ niche, location }),
  });

  if (!response.ok) {
    throw new Error(await parseError(response, "Scrape request failed."));
  }

  return response.json();
}

/**
 * Fetch current status / progress / result for a scrape task.
 *
 * @param taskId - ID returned by enqueueScrape
 * @param token - Clerk JWT
 */
export async function getTaskStatus(
  taskId: string,
  token?: string | null,
): Promise<TaskStatusResponse> {
  const response = await fetch(`${API_BASE}/api/tasks/${taskId}`, {
    headers: buildHeaders(token),
  });

  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to fetch task status."));
  }

  return response.json();
}

/**
 * Refresh Clerk session JWT for a request.
 *
 * Clerk tokens expire ~60s — scrapes poll longer, so callers must refresh
 * per request instead of reusing one token for the whole job.
 */
export type TokenProvider = () => Promise<string | null>;

/**
 * Poll a task until it succeeds or fails, calling onProgress on each tick.
 *
 * Refreshes the Clerk JWT on every poll so long scrapes don't hit 401.
 *
 * @param taskId - Celery task id
 * @param getToken - Async Clerk token provider (refreshed each poll)
 * @param onProgress - Invoked with each poll response
 */
export async function pollTaskUntilDone(
  taskId: string,
  getToken?: TokenProvider | null,
  onProgress?: (status: TaskStatusResponse) => void,
): Promise<TaskStatusResponse> {
  const started = Date.now();

  while (Date.now() - started < POLL_TIMEOUT_MS) {
    // Fresh JWT each tick — session tokens expire before typical scrape duration
    const token = getToken ? await getToken() : null;
    const status = await getTaskStatus(taskId, token);
    onProgress?.(status);

    if (status.status === "SUCCESS") return status;
    if (status.status === "FAILURE") {
      throw new Error(status.error ?? "Scrape task failed.");
    }

    await sleep(POLL_INTERVAL_MS);
  }

  throw new Error("Scrape timed out. Check Celery worker logs and try again.");
}

/**
 * Fetch scrape history for the authenticated user.
 *
 * @param token - Clerk JWT
 */
export async function getScrapeHistory(
  token?: string | null,
): Promise<ScrapeHistoryResponse> {
  const response = await fetch(`${API_BASE}/api/history`, {
    headers: buildHeaders(token),
  });

  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load history."));
  }

  return response.json();
}

/**
 * Fetch a historical scrape job with all leads.
 *
 * @param jobId - ScrapeJob primary key
 * @param token - Clerk JWT
 */
export async function getScrapeJobDetail(
  jobId: number,
  token?: string | null,
): Promise<ScrapeJobDetailResponse> {
  const response = await fetch(`${API_BASE}/api/history/${jobId}`, {
    headers: buildHeaders(token),
  });

  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load job details."));
  }

  return response.json();
}

/**
 * Fetch the currently configured CRM webhook URL.
 *
 * @param token - Clerk JWT
 */
export async function getWebhookConfig(
  token?: string | null,
): Promise<WebhookStatusResponse> {
  const response = await fetch(`${API_BASE}/api/webhooks/configure`, {
    headers: buildHeaders(token),
  });

  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load webhook settings."));
  }

  return response.json();
}

/**
 * Save a CRM / sequencer webhook URL for automatic lead delivery.
 *
 * @param webhookUrl - HTTPS endpoint
 * @param token - Clerk JWT
 */
export async function configureWebhook(
  webhookUrl: string,
  token?: string | null,
): Promise<WebhookConfigureResponse> {
  const response = await fetch(`${API_BASE}/api/webhooks/configure`, {
    method: "POST",
    headers: buildHeaders(token, true),
    body: JSON.stringify({ webhook_url: webhookUrl }),
  });

  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to save webhook URL."));
  }

  return response.json();
}

/**
 * Delay helper for polling intervals.
 *
 * @param ms - Milliseconds to wait
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
