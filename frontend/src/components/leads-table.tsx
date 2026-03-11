"use client";

import { useState } from "react";
import type { Lead } from "@/types/lead";
import { exportLeadsToCsv } from "@/lib/csv-export";

interface LeadsTableProps {
  leads: Lead[];
  message?: string;
}

/**
 * Tabular view of scraped leads with tech stack, email sequences, and CSV export.
 */
export function LeadsTable({ leads, message }: LeadsTableProps) {
  const verifiedCount = leads.filter((lead) => lead.verified_email).length;
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

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
        <table className="min-w-full divide-y divide-ink/10 text-sm">
          <thead className="bg-paper">
            <tr>
              <th className="px-4 py-3 text-left font-semibold text-ink">
                Company
              </th>
              <th className="px-4 py-3 text-left font-semibold text-ink">
                Decision Maker
              </th>
              <th className="px-4 py-3 text-left font-semibold text-ink">
                Title
              </th>
              <th className="px-4 py-3 text-left font-semibold text-ink">
                Email
              </th>
              <th className="px-4 py-3 text-left font-semibold text-ink">
                Tech
              </th>
              <th className="min-w-[260px] px-4 py-3 text-left font-semibold text-ink">
                Sequence
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink/10">
            {leads.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-ink/50">
                  No leads yet. Run a search above to get started.
                </td>
              </tr>
            ) : (
              leads.map((lead) => {
                const rowKey = `${lead.company_name}-${lead.decision_maker_name}`;
                const isExpanded = expandedKey === rowKey;

                return (
                  <tr key={rowKey} className="align-top hover:bg-paper/70">
                    <td className="whitespace-nowrap px-4 py-4 font-medium text-ink">
                      {lead.company_name}
                      {lead.enrichment_source &&
                      lead.enrichment_source !== "scrape" ? (
                        <span className="mt-1 block text-[10px] uppercase tracking-wide text-ink/45">
                          via {lead.enrichment_source}
                        </span>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-ink">
                      {lead.decision_maker_name}
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-ink/65">
                      {lead.title}
                    </td>
                    <td className="px-4 py-4">
                      {lead.verified_email ? (
                        <span className="bg-ink px-2 py-0.5 text-xs font-medium text-paper">
                          {lead.verified_email}
                        </span>
                      ) : (
                        <span className="text-xs text-ink/40">Not verified</span>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex max-w-[160px] flex-wrap gap-1">
                        {(lead.tech_stack ?? []).length > 0 ? (
                          lead.tech_stack.map((tech) => (
                            <span
                              key={tech}
                              className="border border-ink/20 bg-paper px-1.5 py-0.5 text-xs text-ink"
                            >
                              {tech}
                            </span>
                          ))
                        ) : (
                          <span className="text-xs text-ink/35">—</span>
                        )}
                      </div>
                    </td>
                    <td className="max-w-sm px-4 py-4 text-xs leading-relaxed text-ink/65">
                      {lead.email_1_initial || lead.custom_icebreaker ? (
                        <div>
                          <p className="line-clamp-2 italic">
                            {lead.custom_icebreaker ||
                              lead.email_1_initial.slice(0, 120)}
                          </p>
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedKey(isExpanded ? null : rowKey)
                            }
                            className="mt-1 font-medium text-ink underline-offset-2 hover:underline"
                          >
                            {isExpanded ? "Hide sequence" : "View sequence"}
                          </button>
                          {isExpanded ? (
                            <div className="mt-2 space-y-3 border border-ink/15 bg-paper p-3 text-left">
                              <div>
                                <p className="font-semibold text-ink">
                                  Email 1 — Initial
                                </p>
                                <p className="mt-1 whitespace-pre-wrap">
                                  {lead.email_1_initial}
                                </p>
                              </div>
                              <div>
                                <p className="font-semibold text-ink">
                                  Email 2 — Follow-up
                                </p>
                                <p className="mt-1 whitespace-pre-wrap">
                                  {lead.email_2_followup}
                                </p>
                              </div>
                              <div>
                                <p className="font-semibold text-ink">
                                  Email 3 — Breakup
                                </p>
                                <p className="mt-1 whitespace-pre-wrap">
                                  {lead.email_3_breakup}
                                </p>
                              </div>
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <span className="text-ink/35">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
