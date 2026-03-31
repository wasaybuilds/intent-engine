/** A single enriched B2B lead returned by the scraper API. */
export interface Lead {
  company_name: string;
  /** Company website URL — empty string when the business has no site */
  website: string;
  decision_maker_name: string;
  title: string;
  verified_email: string;
  tech_stack: string[];
  recent_news: string | null;
  custom_icebreaker: string;
  email_1_initial: string;
  email_2_followup: string;
  email_3_breakup: string;
  enrichment_source: string;
}

/** Final scrape payload when a task completes successfully. */
export interface ScrapeResponse {
  leads: Lead[];
  total: number;
  message: string;
}

/** Immediate response from POST /api/scrape. */
export interface TaskSubmitResponse {
  task_id: string;
  status: "PENDING";
}

/** Live progress metadata while a Celery job runs. */
export interface TaskProgress {
  step: string;
  detail: string;
  percent: number;
  companies_found: number;
  companies_processed: number;
}

/** Pollable task status from GET /api/tasks/{task_id}. */
export interface TaskStatusResponse {
  task_id: string;
  status: string;
  progress: TaskProgress | null;
  result: ScrapeResponse | null;
  error: string | null;
}

/** Webhook configuration status. */
export interface WebhookStatusResponse {
  webhook_url: string | null;
  configured: boolean;
}

/** Confirmation after saving a webhook URL. */
export interface WebhookConfigureResponse {
  webhook_url: string;
  message: string;
}

/** Summary row in scrape history. */
export interface ScrapeJobSummary {
  id: number;
  task_id: string;
  status: string;
  niche: string;
  location: string;
  message: string | null;
  lead_count: number;
  created_at: string;
}

/** List of past scrape jobs. */
export interface ScrapeHistoryResponse {
  jobs: ScrapeJobSummary[];
  total: number;
}

/** Full historical job with leads. */
export interface ScrapeJobDetailResponse {
  id: number;
  task_id: string;
  status: string;
  niche: string;
  location: string;
  message: string | null;
  created_at: string;
  leads: Lead[];
}
