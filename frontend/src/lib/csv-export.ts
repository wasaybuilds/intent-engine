import type { Lead } from "@/types/lead";

/**
 * Escape a CSV field value per RFC 4180.
 *
 * @param value - Raw cell value
 * @returns Quoted and escaped string safe for CSV
 */
function escapeCsvField(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/**
 * Build a CSV string from lead records and trigger a browser download.
 *
 * @param leads - Rows to export
 * @param filename - Download filename (defaults to timestamped name)
 */
export function exportLeadsToCsv(
  leads: Lead[],
  filename?: string,
): void {
  const headers = [
    "Company Name",
    "Website",
    "Decision Maker Name",
    "Title",
    "Verified Email",
    "Personal Phone",
    "Public Phone",
    "Personal Phone Verified",
    "Public Phone Verified",
    "Tech Stack",
    "Recent News",
    "Enrichment Source",
    "AI Icebreaker",
    "Email 1 Initial",
    "Email 2 Followup",
    "Email 3 Breakup",
  ];

  const rows = leads.map((lead) =>
    [
      lead.company_name,
      lead.website ?? "",
      lead.decision_maker_name,
      lead.title,
      lead.verified_email,
      lead.personal_phone ?? "",
      lead.public_phone ?? "",
      lead.personal_phone_verified ? "yes" : "no",
      lead.public_phone_verified ? "yes" : "no",
      (lead.tech_stack ?? []).join("; "),
      lead.recent_news ?? "",
      lead.enrichment_source ?? "scrape",
      lead.custom_icebreaker ?? "",
      lead.email_1_initial ?? "",
      lead.email_2_followup ?? "",
      lead.email_3_breakup ?? "",
    ]
      .map(escapeCsvField)
      .join(","),
  );

  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download =
    filename ??
    `leads-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
  link.click();

  URL.revokeObjectURL(url);
}
