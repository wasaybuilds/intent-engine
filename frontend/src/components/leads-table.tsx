"use client";

import { useEffect, useMemo, useState } from "react";
import type { Lead } from "@/types/lead";
import { exportLeadsToCsv } from "@/lib/csv-export";
import { LeadDetailDrawer } from "@/components/lead-detail-drawer";

interface LeadsTableProps {
  leads: Lead[];
  message?: string;
}

const PAGE_SIZE = 10;

/**
 * Tabular view of scraped leads with website status, CSV export,
 * pagination, and a per-lead detail drawer opened by row click.
 */
export function LeadsTable({ leads, message }: LeadsTableProps) {
  const verifiedCount = leads.filter((lead) => lead.verified_email).length;
  const noSiteCount = leads.filter((lead) => !lead.website).length;
  const phoneCount = leads.filter(
    (lead) => lead.personal_phone || lead.public_phone,
  ).length;
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [page, setPage] = useState(1);

  const totalPages = Math.max(1, Math.ceil(leads.length / PAGE_SIZE));

  // Reset to first page when a new scrape result set arrives
  useEffect(() => {
    setPage(1);
  }, [leads]);

  // Clamp page if results shrink (e.g. after filtering)
  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const pageLeads = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return leads.slice(start, start + PAGE_SIZE);
  }, [leads, page]);

  const rangeStart = leads.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, leads.length);

  return (
    <div className="panel">
      <div className="flex flex-col gap-3 border-b border-ink/10 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-display text-lg font-semibold text-ink">
            Results ({leads.length})
          </h2>
          {message ? (
            <p className="mt-0.5 text-sm text-ink/65">{message}</p>
          ) : null}
          <p className="mt-1 text-xs text-ink/45">
            {verifiedCount} verified email{verifiedCount === 1 ? "" : "s"}
            {noSiteCount > 0
              ? ` · ${noSiteCount} without a website`
              : ""}
            {phoneCount > 0 ? ` · ${phoneCount} with phone` : ""}
            {leads.length > 0 ? " · Click a row for full details" : ""}
          </p>
        </div>

        <button
          type="button"
          onClick={() => exportLeadsToCsv(leads)}
          disabled={leads.length === 0}
          className="btn-secondary"
        >
          Export CSV
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="leads-table w-full min-w-[1100px] border-collapse text-sm">
          <thead>
            <tr className="leads-thead">
              <th className="w-[18%] min-w-[180px] px-5 py-3.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-ink/55">
                Company
              </th>
              <th className="w-[16%] min-w-[160px] px-5 py-3.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-ink/55">
                Website
              </th>
              <th className="w-[16%] min-w-[160px] px-5 py-3.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-ink/55">
                Decision Maker
              </th>
              <th className="w-[14%] min-w-[140px] px-5 py-3.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-ink/55">
                Title
              </th>
              <th className="w-[20%] min-w-[200px] px-5 py-3.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-ink/55">
                Email
              </th>
              <th className="w-[18%] min-w-[180px] px-5 py-3.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-ink/55">
                Phones
              </th>
            </tr>
          </thead>
          <tbody>
            {leads.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-14 text-center text-ink/50">
                  No leads yet. Run a search above to get started.
                </td>
              </tr>
            ) : (
              pageLeads.map((lead, index) => {
                const rowKey = `${lead.company_name}-${lead.decision_maker_name}-${index}`;
                const isSelected =
                  selectedLead?.company_name === lead.company_name &&
                  selectedLead?.decision_maker_name === lead.decision_maker_name;

                return (
                  <tr
                    key={rowKey}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedLead(lead)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedLead(lead);
                      }
                    }}
                    className={`leads-row cursor-pointer border-t border-ink/8 align-top transition-colors ${
                      isSelected ? "bg-ink/[0.06]" : "hover:bg-paper"
                    }`}
                  >
                    <td className="px-5 py-4 font-medium text-ink">
                      <span className="block max-w-[220px] truncate" title={lead.company_name}>
                        {lead.company_name}
                      </span>
                      {lead.enrichment_source &&
                      lead.enrichment_source !== "scrape" ? (
                        <span className="mt-1 block text-[10px] uppercase tracking-wide text-ink/45">
                          via {lead.enrichment_source}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-5 py-4">
                      {lead.website ? (
                        <a
                          href={lead.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block max-w-[200px] truncate text-sm text-ink underline underline-offset-2"
                          title={lead.website}
                          onClick={(event) => event.stopPropagation()}
                        >
                          {formatWebsiteLabel(lead.website)}
                        </a>
                      ) : (
                        <span className="inline-flex border border-ink/20 bg-ink/5 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink/60">
                          No site
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-4 text-ink">
                      <span
                        className="block max-w-[180px] truncate"
                        title={lead.decision_maker_name}
                      >
                        {lead.decision_maker_name}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-ink/70">
                      <span className="block max-w-[160px] truncate" title={lead.title}>
                        {lead.title || "—"}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      {lead.verified_email ? (
                        <span
                          className="inline-block max-w-[240px] truncate bg-ink px-2.5 py-1 text-xs font-medium text-paper"
                          title={lead.verified_email}
                        >
                          {lead.verified_email}
                        </span>
                      ) : (
                        <span className="text-xs text-ink/40">Not verified</span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex max-w-[220px] flex-col gap-1 text-xs">
                        {lead.personal_phone ? (
                          <span title={lead.personal_phone}>
                            <span className="text-ink/45">Personal · </span>
                            <span className="font-medium text-ink">
                              {lead.personal_phone}
                            </span>
                            {lead.personal_phone_verified ? (
                              <span className="ml-1 text-[10px] uppercase text-ink/40">
                                ✓✓
                              </span>
                            ) : null}
                          </span>
                        ) : null}
                        {lead.public_phone ? (
                          <span title={lead.public_phone}>
                            <span className="text-ink/45">Public · </span>
                            <span className="text-ink/80">{lead.public_phone}</span>
                            {lead.public_phone_verified ? (
                              <span className="ml-1 text-[10px] uppercase text-ink/40">
                                ✓✓
                              </span>
                            ) : null}
                          </span>
                        ) : null}
                        {!lead.personal_phone && !lead.public_phone ? (
                          <span className="text-ink/35">—</span>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {leads.length > 0 ? (
        <div className="flex flex-col gap-3 border-t border-ink/10 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-ink/50">
            Showing {rangeStart}–{rangeEnd} of {leads.length}
          </p>

          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn-ghost"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              Previous
            </button>

            <div className="flex items-center gap-1">
              {Array.from({ length: totalPages }, (_, index) => index + 1).map(
                (pageNumber) => (
                  <button
                    key={pageNumber}
                    type="button"
                    onClick={() => setPage(pageNumber)}
                    className={`min-w-[2rem] rounded-sm px-2 py-1.5 text-xs font-semibold ${
                      pageNumber === page
                        ? "bg-ink text-paper"
                        : "text-ink/60 hover:bg-paper hover:text-ink"
                    }`}
                    aria-current={pageNumber === page ? "page" : undefined}
                  >
                    {pageNumber}
                  </button>
                ),
              )}
            </div>

            <button
              type="button"
              className="btn-ghost"
              disabled={page >= totalPages}
              onClick={() =>
                setPage((current) => Math.min(totalPages, current + 1))
              }
            >
              Next
            </button>
          </div>
        </div>
      ) : null}

      <LeadDetailDrawer
        lead={selectedLead}
        onClose={() => setSelectedLead(null)}
      />
    </div>
  );
}

/**
 * Shorten a URL to its hostname for compact table display.
 *
 * @param url - Full website URL
 * @returns Hostname without "www." prefix
 */
function formatWebsiteLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
