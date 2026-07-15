"use client";

import type { TaskProgress } from "@/types/lead";

const PIPELINE_STEPS = [
  { key: "PENDING", label: "Queued — waiting for worker" },
  { key: "DISCOVERY", label: "Searching business directories" },
  { key: "ENRICHMENT", label: "Enriching contacts & signals" },
  { key: "VALIDATION", label: "Validating emails" },
  { key: "FORMATTING", label: "Formatting results" },
  { key: "WEBHOOK", label: "Delivering to webhook" },
];

interface LoadingStateProps {
  progress?: TaskProgress | null;
  taskStatus?: string;
  niche?: string;
  location?: string;
}

/**
 * Pipeline progress panel — static indicators, no spin animation.
 */
export function LoadingState({
  progress,
  taskStatus,
  niche,
  location,
}: LoadingStateProps) {
  const activeStep = (progress?.step || taskStatus || "PENDING").toUpperCase();
  const activeIndex = Math.max(
    0,
    PIPELINE_STEPS.findIndex((step) => activeStep.includes(step.key)),
  );
  const percent = progress?.percent ?? 0;
  const searchLabel =
    niche && location ? `${niche} · ${location}` : niche || location || "";

  return (
    <div role="status" aria-live="polite" className="panel p-8">
      <div className="mx-auto max-w-md">
        <h2 className="font-display text-xl font-semibold text-ink">
          Scraping in progress
        </h2>
        {searchLabel ? (
          <p className="mt-1 text-sm font-medium text-ink">{searchLabel}</p>
        ) : null}
        <p className="mt-1 text-sm text-ink/60">
          Safe to open History or switch tabs — come back here and progress
          continues. Only one scrape runs at a time.
        </p>
        {progress?.detail ? (
          <p className="mt-3 text-sm text-ink">{progress.detail}</p>
        ) : null}

        <div className="mt-5 h-1.5 w-full overflow-hidden bg-paper">
          <div
            className="h-full bg-ink"
            style={{ width: `${Math.min(100, Math.max(percent, 4))}%` }}
          />
        </div>
        <p className="mt-1.5 text-xs text-ink/50">{percent}% complete</p>

        <ul className="mt-6 space-y-2.5 text-sm">
          {PIPELINE_STEPS.map((step, index) => {
            const isDone = index < activeIndex;
            const isActive = index === activeIndex;

            return (
              <li key={step.key} className="flex items-center gap-3">
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center text-xs font-medium ${
                    isActive
                      ? "bg-ink text-paper"
                      : isDone
                        ? "bg-ink/15 text-ink"
                        : "bg-paper text-ink/35"
                  }`}
                >
                  {isDone ? "✓" : index + 1}
                </span>
                <span
                  className={
                    isActive
                      ? "font-medium text-ink"
                      : isDone
                        ? "text-ink/70"
                        : "text-ink/40"
                  }
                >
                  {step.label}
                </span>
              </li>
            );
          })}
        </ul>

        {progress &&
        (progress.companies_found > 0 || progress.companies_processed > 0) ? (
          <p className="mt-5 text-xs text-ink/50">
            Companies: {progress.companies_processed}/
            {progress.companies_found || "—"}
          </p>
        ) : null}
      </div>
    </div>
  );
}
