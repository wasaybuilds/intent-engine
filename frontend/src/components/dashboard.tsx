"use client";

import { useAuth } from "@clerk/nextjs";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { enqueueScrape, pollTaskUntilDone } from "@/lib/api";
import type { Lead, TaskProgress } from "@/types/lead";
import { LeadsTable } from "@/components/leads-table";
import { LoadingState } from "@/components/loading-state";
import { ScrapeForm } from "@/components/scrape-form";
import { SettingsPanel } from "@/components/settings-panel";

/**
 * Main dashboard: enqueue scrape jobs, poll Celery progress, show results.
 */
export function Dashboard() {
  const { getToken } = useAuth();
  const [niche, setNiche] = useState("");
  const [location, setLocation] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [taskStatus, setTaskStatus] = useState<string>("");
  const [settingsOpen, setSettingsOpen] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setIsLoading(true);
    setLeads([]);
    setProgress(null);
    setTaskStatus("PENDING");

    try {
      const token = await getToken();
      const { task_id } = await enqueueScrape(niche.trim(), location.trim(), token);

      // Pass getToken so each poll refreshes the JWT (Clerk tokens expire ~60s)
      const finalStatus = await pollTaskUntilDone(task_id, getToken, (status) => {
        setTaskStatus(status.status);
        if (status.progress) setProgress(status.progress);
      });

      setLeads(finalStatus.result?.leads ?? []);
      setMessage(finalStatus.result?.message ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setIsLoading(false);
      setProgress(null);
      setTaskStatus("");
    }
  }

  return (
    <AppShell
      topAction={
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          className="btn-secondary"
        >
          Webhook
        </button>
      }
    >
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Find decision makers
          </h1>
          <p className="mt-2 max-w-2xl text-ink/65">
            Search by niche and city. We scrape public sites, enrich contacts,
            and draft a 3-step outreach sequence.
          </p>
        </header>

        <ScrapeForm
          niche={niche}
          location={location}
          isLoading={isLoading}
          onNicheChange={setNiche}
          onLocationChange={setLocation}
          onSubmit={handleSubmit}
        />

        {error ? (
          <div
            role="alert"
            className="border border-ink/20 bg-ink/5 px-4 py-3 text-sm text-ink"
          >
            {error}
          </div>
        ) : null}

        {isLoading ? (
          <LoadingState progress={progress} taskStatus={taskStatus} />
        ) : (
          <LeadsTable leads={leads} message={message} />
        )}
      </div>

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        getToken={getToken}
      />
    </AppShell>
  );
}
