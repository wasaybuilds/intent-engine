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
    { step: "01", label: "Initial", body: lead.email_1_initial },
    { step: "02", label: "Follow-up", body: lead.email_2_followup },
    { step: "03", label: "Breakup", body: lead.email_3_breakup },
  ].filter((email) => email.body);
  const initials = lead.company_name
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

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
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center border border-paper/25 bg-paper/10 font-display text-sm font-semibold">
              {initials}
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] opacity-55">
                Lead profile
              </p>
              <h2 className="truncate font-display text-lg font-semibold">
                {lead.company_name}
              </h2>
            </div>
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

        <div className="flex-1 space-y-4 overflow-y-auto p-5 text-sm">
          <section className="border border-ink/10 bg-white">
            <div className="border-b border-ink/10 px-4 py-3">
              <h3 className="font-display font-semibold text-ink">Contact</h3>
              <p className="mt-0.5 text-xs text-ink/45">
                Decision maker and reachable channels
              </p>
            </div>

            <div className="divide-y divide-ink/10">
              <DetailRow label="Decision maker">
                <p className="font-medium text-ink">
                  {lead.decision_maker_name || "Not found"}
                </p>
                <p className="text-xs text-ink/55">
                  {lead.title || "Title unavailable"}
                  {lead.enrichment_source
                    ? ` · ${formatSource(lead.enrichment_source)}`
                    : ""}
                </p>
              </DetailRow>

              <DetailRow label="Email">
                {lead.verified_email ? (
                  <a
                    href={`mailto:${lead.verified_email}`}
                    className="break-all font-medium text-ink underline-offset-2 hover:underline"
                  >
                    {lead.verified_email}
                  </a>
                ) : (
                  <EmptyValue>Not found</EmptyValue>
                )}
              </DetailRow>

              <DetailRow label="Personal / owner">
                {lead.personal_phone ? (
                  <PhoneValue
                    phone={lead.personal_phone}
                    validated={lead.personal_phone_verified}
                  />
                ) : (
                  <EmptyValue>Not found publicly</EmptyValue>
                )}
              </DetailRow>

              <DetailRow label="Public / business">
                {lead.public_phone ? (
                  <PhoneValue
                    phone={lead.public_phone}
                    validated={lead.public_phone_verified}
                  />
                ) : (
                  <EmptyValue>Not found</EmptyValue>
                )}
              </DetailRow>

              <DetailRow label="Website">
                {hasWebsite ? (
                  <a
                    href={lead.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block max-w-full truncate font-medium text-ink underline-offset-2 hover:underline"
                    title={lead.website}
                  >
                    {lead.website}
                  </a>
                ) : (
                  <span className="inline-flex border border-ink/15 bg-ink/5 px-2 py-1 text-xs font-medium text-ink/60">
                    No website found
                  </span>
                )}
              </DetailRow>
            </div>
          </section>

          <section className="border border-ink/10 bg-white">
            <div className="border-b border-ink/10 px-4 py-3">
              <h3 className="font-display font-semibold text-ink">
                Business intelligence
              </h3>
              <p className="mt-0.5 text-xs text-ink/45">
                Signals collected from the company site
              </p>
            </div>
            <div className="space-y-4 p-4">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink/40">
                  Tech stack
                </p>
                {(lead.tech_stack ?? []).length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {lead.tech_stack.map((tech) => (
                      <span
                        key={tech}
                        className="border border-ink/15 bg-paper px-2 py-1 text-xs text-ink"
                      >
                        {tech}
                      </span>
                    ))}
                  </div>
                ) : (
                  <EmptyValue>None detected</EmptyValue>
                )}
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink/40">
                  Recent news
                </p>
                <p className="mt-1 leading-relaxed text-ink/70">
                  {lead.recent_news || "No recent signal found"}
                </p>
              </div>
            </div>
          </section>

          {lead.custom_icebreaker ? (
            <section className="border border-ink/10 bg-white p-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink/40">
                Suggested icebreaker
              </p>
              <p className="mt-2 border-l-2 border-ink/20 pl-3 italic leading-relaxed text-ink/70">
                {lead.custom_icebreaker}
              </p>
            </section>
          ) : null}

          {emails.length > 0 ? (
            <section className="border border-ink/10 bg-white">
              <div className="border-b border-ink/10 px-4 py-3">
                <h3 className="font-display font-semibold text-ink">
                  Outreach sequence
                </h3>
                <p className="mt-0.5 text-xs text-ink/45">
                  Three-touch personalized campaign
                </p>
              </div>
              <div className="divide-y divide-ink/10">
                {emails.map((email) => (
                  <div key={email.label} className="grid grid-cols-[2.25rem_1fr] gap-3 p-4">
                    <span className="flex h-8 w-8 items-center justify-center bg-ink text-[10px] font-semibold text-paper">
                      {email.step}
                    </span>
                    <div className="min-w-0">
                      <p className="font-semibold text-ink">{email.label}</p>
                      <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-ink/65">
                        {email.body}
                      </p>
                    </div>
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

interface DetailRowProps {
  label: string;
  children: React.ReactNode;
}

/** Render a consistently aligned label/value row. */
function DetailRow({ label, children }: DetailRowProps) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3 px-4 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-ink/40">
        {label}
      </p>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** Render a muted missing-data value. */
function EmptyValue({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs text-ink/40">{children}</p>;
}

/** Render a callable phone with an honest structural-validation badge. */
function PhoneValue({
  phone,
  validated,
}: {
  phone: string;
  validated: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <a
        href={`tel:${phone}`}
        className="font-medium text-ink underline-offset-2 hover:underline"
      >
        {phone}
      </a>
      {validated ? (
        <span className="border border-ink/15 bg-ink/5 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-ink/55">
          Format validated
        </span>
      ) : null}
    </div>
  );
}

/** Convert internal enrichment source keys into readable labels. */
function formatSource(source: string): string {
  if (source === "scrape") return "Company website";
  if (source === "partial") return "Partial lead";
  return source;
}
