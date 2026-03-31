"use client";

import { useEffect } from "react";
import type { Lead } from "@/types/lead";

interface LeadDetailDrawerProps {
  lead: Lead | null;
  onClose: () => void;
}

/**
 * Right-hand drawer showing every field of a scraped lead:
 * contact info, website (or a "no website" notice), tech stack,
 * recent news, icebreaker, and the full 3-step email sequence.
 */
export function LeadDetailDrawer({ lead, onClose }: LeadDetailDrawerProps) {
  // Close on Escape for keyboard accessibility
  useEffect(() => {
    if (!lead) return;

    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [lead, onClose]);

  if (!lead) return null;

  const hasWebsite = Boolean(lead.website);
  const emails = [
    { label: "Email 1 — Initial", body: lead.email_1_initial },
    { label: "Email 2 — Follow-up", body: lead.email_2_followup },
    { label: "Email 3 — Breakup", body: lead.email_3_breakup },
  ].filter((email) => email.body);

  return (
    <>
      <button
        type="button"
        aria-label="Close lead details"
        className="drawer-backdrop"
        onClick={onClose}
      />

      <aside className="drawer-panel" role="dialog" aria-label="Lead details">
        <div className="drawer-header">
          <div>
            <h2 className="font-display text-lg font-semibold">
              {lead.company_name}
            </h2>
            <p className="text-xs" style={{ opacity: 0.65 }}>
              Lead details
            </p>
          </div>
          <button
            type="button"
            className="drawer-close"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6 text-sm">
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/45">
              Website
            </h3>
            {hasWebsite ? (
              <a
                href={lead.website}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-block break-all font-medium text-ink underline underline-offset-2"
              >
                {lead.website}
              </a>
            ) : (
              <p className="mt-1 inline-flex items-center gap-2 border border-ink/20 bg-ink/5 px-2 py-1 text-xs font-medium text-ink/70">
                No website found for this business
              </p>
            )}
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/45">
              Decision maker
            </h3>
            <p className="mt-1 font-medium text-ink">
              {lead.decision_maker_name || "—"}
            </p>
            {lead.title ? <p className="text-ink/65">{lead.title}</p> : null}
            {lead.enrichment_source && lead.enrichment_source !== "scrape" ? (
              <p className="mt-1 text-[10px] uppercase tracking-wide text-ink/45">
                via {lead.enrichment_source}
              </p>
            ) : null}
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/45">
              Email
            </h3>
            {lead.verified_email ? (
              <span className="mt-1 inline-block bg-ink px-2 py-0.5 text-xs font-medium text-paper">
                {lead.verified_email}
              </span>
            ) : (
              <p className="mt-1 text-xs text-ink/40">Not verified</p>
            )}
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/45">
              Tech stack
            </h3>
            {(lead.tech_stack ?? []).length > 0 ? (
              <div className="mt-1 flex flex-wrap gap-1">
                {lead.tech_stack.map((tech) => (
                  <span
                    key={tech}
                    className="border border-ink/20 bg-paper px-1.5 py-0.5 text-xs text-ink"
                  >
                    {tech}
                  </span>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-xs text-ink/40">None detected</p>
            )}
          </section>

          {lead.recent_news ? (
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/45">
                Recent news
              </h3>
              <p className="mt-1 text-ink/75">{lead.recent_news}</p>
            </section>
          ) : null}

          {lead.custom_icebreaker ? (
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/45">
                Icebreaker
              </h3>
              <p className="mt-1 italic text-ink/75">{lead.custom_icebreaker}</p>
            </section>
          ) : null}

          {emails.length > 0 ? (
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/45">
                Outreach sequence
              </h3>
              <div className="mt-2 space-y-4">
                {emails.map((email) => (
                  <div
                    key={email.label}
                    className="border border-ink/15 bg-paper p-3"
                  >
                    <p className="font-semibold text-ink">{email.label}</p>
                    <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-ink/70">
                      {email.body}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </aside>
    </>
  );
}
