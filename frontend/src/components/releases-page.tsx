"use client";

import { AppShell } from "@/components/app-shell";

interface ReleaseSection {
  heading: string;
  items: string[];
}

interface Release {
  version: string;
  date: string;
  summary: string;
  sections: ReleaseSection[];
}

/**
 * Release notes shown in-app. Mirror CHANGELOG.md when shipping a version.
 */
const RELEASES: Release[] = [
  {
    version: "1.1.0",
    date: "July 15, 2026",
    summary: "Lead detail view, website visibility, and enrichment fixes.",
    sections: [
      {
        heading: "Added",
        items: [
          "Lead detail view — open a full drawer per lead with website, contact, tech stack, news, and the complete 3-step email sequence.",
          "Website column on results — businesses without a site are flagged with a \"No site\" badge instead of being dropped.",
          "Partial leads — companies with no named decision maker are kept as \"Owner / Team\" rows.",
          "New branded favicon and this in-app Releases page.",
        ],
      },
      {
        heading: "Fixed",
        items: [
          "Hunter.io enrichment failed with HTTP 400 on free plans, causing scrapes to return zero leads.",
          "Contact selection now accepts named personal emails when no executive title is found.",
          "Broader decision-maker title matching (General Manager, Operations Manager, Owner, Proprietor).",
        ],
      },
    ],
  },
  {
    version: "1.0.0",
    date: "March 31, 2026",
    summary: "Initial public release of Intent Engine.",
    sections: [
      {
        heading: "Highlights",
        items: [
          "Niche + location Google Maps discovery (Playwright).",
          "LLM decision-maker extraction and 3-step email sequences.",
          "Hunter.io / Apollo enrichment fallbacks.",
          "Clerk auth, PostgreSQL history, Celery jobs.",
          "CSV export, CRM webhooks, location autocomplete.",
        ],
      },
    ],
  },
];

/**
 * Releases page — human-readable changelog for the app.
 */
export function ReleasesPage() {
  return (
    <AppShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        <header>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">
            Releases
          </h1>
          <p className="mt-2 max-w-2xl text-ink/65">
            What&apos;s new in Intent Engine.
          </p>
        </header>

        <div className="flex flex-col gap-6">
          {RELEASES.map((release) => (
            <article key={release.version} className="panel px-6 py-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink/10 pb-3">
                <h2 className="font-display text-xl font-semibold text-ink">
                  v{release.version}
                </h2>
                <span className="text-xs text-ink/45">{release.date}</span>
              </div>

              <p className="mt-3 text-sm text-ink/75">{release.summary}</p>

              {release.sections.map((section) => (
                <section key={section.heading} className="mt-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/45">
                    {section.heading}
                  </h3>
                  <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-ink/75">
                    {section.items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              ))}
            </article>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
