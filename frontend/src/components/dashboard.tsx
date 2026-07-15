"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { enqueueScrape, pollTaskUntilDone } from "@/lib/api";
import {
  clearActiveScrape,
  loadActiveScrape,
  saveActiveScrape,
} from "@/lib/active-scrape";
import type { Lead, TaskProgress } from "@/types/lead";
import { LeadsTable } from "@/components/leads-table";
import { LoadingState } from "@/components/loading-state";
import { ScrapeForm } from "@/components/scrape-form";
import { SettingsPanel } from "@/components/settings-panel";

/**
 * Main dashboard: enqueue scrape jobs, poll Celery progress, show results.
 *
 * Active task id is stored in sessionStorage so switching to History (or
 * another in-app page) and back resumes the same job instead of looking idle.
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
  // Guard against Strict Mode double-mount starting two poll loops
  const pollGeneration = useRef(0);

  useEffect(() => {
    const active = loadActiveScrape();
    if (!active) return;

    setNiche(active.niche);
    setLocation(active.location);
    setIsLoading(true);
    setTaskStatus("STARTED");
    setError("");
    setMessage("");
    setLeads([]);

    const generation = ++pollGeneration.current;
    void resumePoll(active.taskId, generation);
    // Resume once on mount — getToken identity is stable enough for this path
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Poll an existing Celery task until done and update dashboard state.
   *
   * @param taskId - Celery task id
   * @param generation - Monotonic id so stale polls ignore setState after unmount/remount
   */
  async function resumePoll(taskId: string, generation: number) {
    try {
      const finalStatus = await pollTaskUntilDone(taskId, getToken, (status) => {
        if (generation !== pollGeneration.current) return;
        setTaskStatus(status.status);
        if (status.progress) setProgress(status.progress);
      });

      if (generation !== pollGeneration.current) return;

      setLeads(finalStatus.result?.leads ?? []);
      setMessage(finalStatus.result?.message ?? "");
      clearActiveScrape();
    } catch (err) {
      if (generation !== pollGeneration.current) return;
      setError(err instanceof Error ? err.message : "Something went wrong.");
      clearActiveScrape();
    } finally {
      if (generation === pollGeneration.current) {
        setIsLoading(false);
        setProgress(null);
        setTaskStatus("");
      }
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // One scrape at a time — Celery is still working even if you left the page
    if (isLoading || loadActiveScrape()) {
      setError(
        "A scrape is already running. Wait for it to finish (or open History) before starting another.",
      );
      return;
    }

    setError("");
    setMessage("");
    setIsLoading(true);
    setLeads([]);
    setProgress(null);
    setTaskStatus("PENDING");

    const generation = ++pollGeneration.current;

    try {
      const token = await getToken();
      const trimmedNiche = niche.trim();
      const trimmedLocation = location.trim();
      const { task_id } = await enqueueScrape(
        trimmedNiche,
        trimmedLocation,
        token,
      );

      saveActiveScrape({
        taskId: task_id,
        niche: trimmedNiche,
        location: trimmedLocation,
        startedAt: Date.now(),
      });

      // Pass getToken so each poll refreshes the JWT (Clerk tokens expire ~60s)
      const finalStatus = await pollTaskUntilDone(task_id, getToken, (status) => {
        if (generation !== pollGeneration.current) return;
        setTaskStatus(status.status);
        if (status.progress) setProgress(status.progress);
      });

      if (generation !== pollGeneration.current) return;

      setLeads(finalStatus.result?.leads ?? []);
      setMessage(finalStatus.result?.message ?? "");
      clearActiveScrape();
    } catch (err) {
      if (generation !== pollGeneration.current) return;
      setError(err instanceof Error ? err.message : "Something went wrong.");
      clearActiveScrape();
    } finally {
      if (generation === pollGeneration.current) {
        setIsLoading(false);
        setProgress(null);
        setTaskStatus("");
      }
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
          <LoadingState
            progress={progress}
            taskStatus={taskStatus}
            niche={niche}
            location={location}
          />
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
