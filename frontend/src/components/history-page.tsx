"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";
import { getScrapeHistory, getScrapeJobDetail } from "@/lib/api";
import type { Lead, ScrapeJobSummary } from "@/types/lead";
import { AppShell } from "@/components/app-shell";
import { LeadsTable } from "@/components/leads-table";

/**
 * Scrape history page — view past jobs and re-download lead CSVs.
 */
export function HistoryPage() {
  const { getToken } = useAuth();
  const [jobs, setJobs] = useState<ScrapeJobSummary[]>([]);
  const [selectedLeads, setSelectedLeads] = useState<Lead[]>([]);
  const [selectedJob, setSelectedJob] = useState<ScrapeJobSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [error, setError] = useState("");

  const loadHistory = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const token = await getToken();
      const data = await getScrapeHistory(token);
      setJobs(data.jobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history.");
    } finally {
      setIsLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const hasRunningJob = jobs.some((job) =>
    ["PENDING", "STARTED", "PROGRESS"].includes(job.status),
  );

  // Keep running jobs fresh so History shows live status while Scrape is elsewhere
  useEffect(() => {
    if (!hasRunningJob) return;

    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const token = await getToken();
          const data = await getScrapeHistory(token);
          setJobs(data.jobs);
        } catch {
          // Soft refresh — keep the last good list on transient errors
        }
      })();
    }, 4000);

    return () => window.clearInterval(timer);
  }, [hasRunningJob, getToken]);

  async function handleViewJob(job: ScrapeJobSummary) {
    setIsLoadingDetail(true);
    setError("");
    setSelectedJob(job);
    try {
      const token = await getToken();
      const detail = await getScrapeJobDetail(job.id, token);
      setSelectedLeads(detail.leads);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load leads.");
      setSelectedLeads([]);
    } finally {
      setIsLoadingDetail(false);
    }
  }

  function statusBadgeClass(status: string): string {
    switch (status) {
      case "SUCCESS":
        return "bg-ink/10 text-ink";
      case "FAILURE":
        return "bg-ink text-paper";
      case "PENDING":
      case "STARTED":
      case "PROGRESS":
        return "border border-ink/20 bg-paper text-ink/70";
      default:
        return "bg-paper text-ink/60";
    }
  }

  return (
    <AppShell>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">
            History
          </h1>
          <p className="mt-2 max-w-2xl text-ink/65">
            Review previous scrapes and re-download lead CSVs. Jobs still
            running show as PENDING / STARTED — return to Scrape to watch live
            progress.
          </p>
        </header>

        {error ? (
          <div
            role="alert"
            className="border border-ink/20 bg-ink/5 px-4 py-3 text-sm text-ink"
          >
            {error}
          </div>
        ) : null}

        <div className="panel">
          <div className="border-b border-ink/10 px-6 py-4">
            <h2 className="font-display text-lg font-semibold text-ink">
              Past jobs
            </h2>
          </div>

          {isLoading ? (
            <p className="px-6 py-10 text-center text-sm text-ink/50">
              Loading history…
            </p>
          ) : jobs.length === 0 ? (
            <p className="px-6 py-10 text-center text-sm text-ink/50">
              No scrapes yet. Run your first search from Scrape.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-ink/10 text-sm">
                <thead className="bg-paper">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-ink">
                      Niche
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-ink">
                      Location
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-ink">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-ink">
                      Leads
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-ink">
                      Date
                    </th>
                    <th className="px-4 py-3 text-right font-semibold text-ink">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink/10">
                  {jobs.map((job) => (
                    <tr key={job.id} className="hover:bg-paper/70">
                      <td className="whitespace-nowrap px-4 py-3 font-medium text-ink">
                        {job.niche}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-ink/65">
                        {job.location}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex px-2 py-0.5 text-xs font-medium ${statusBadgeClass(job.status)}`}
                        >
                          {job.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-ink/65">{job.lead_count}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-ink/65">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => handleViewJob(job)}
                          className="text-sm font-medium text-ink underline-offset-2 hover:underline"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {selectedJob ? (
          <div className="space-y-3">
            <h2 className="font-display text-lg font-semibold text-ink">
              {selectedJob.niche} · {selectedJob.location}
            </h2>
            {isLoadingDetail ? (
              <p className="text-center text-sm text-ink/50">Loading leads…</p>
            ) : (
              <LeadsTable leads={selectedLeads} />
            )}
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
