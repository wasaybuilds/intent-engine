"use client";

import { LocationInput } from "@/components/location-input";
import { NicheInput } from "@/components/niche-input";

interface ScrapeFormProps {
  niche: string;
  location: string;
  isLoading: boolean;
  onNicheChange: (value: string) => void;
  onLocationChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
}

const SUGGESTIONS = [
  { niche: "dentists", location: "Austin TX" },
  { niche: "HVAC companies", location: "Dallas TX" },
  { niche: "personal injury lawyers", location: "Miami FL" },
];

/**
 * Search form for niche and location inputs.
 */
export function ScrapeForm({
  niche,
  location,
  isLoading,
  onNicheChange,
  onLocationChange,
  onSubmit,
}: ScrapeFormProps) {
  return (
    <form onSubmit={onSubmit} className="panel p-6">
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label
            htmlFor="niche"
            className="mb-1.5 block text-sm font-medium text-ink"
          >
            Niche
          </label>
          <NicheInput
            id="niche"
            required
            disabled={isLoading}
            placeholder="Pick a niche or type your own…"
            value={niche}
            onChange={onNicheChange}
          />
        </div>

        <div>
          <label
            htmlFor="location"
            className="mb-1.5 block text-sm font-medium text-ink"
          >
            Location
          </label>
          <LocationInput
            id="location"
            required
            disabled={isLoading}
            placeholder="Start typing a city…"
            value={location}
            onChange={onLocationChange}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {SUGGESTIONS.map((item) => (
          <button
            key={`${item.niche}-${item.location}`}
            type="button"
            disabled={isLoading}
            onClick={() => {
              onNicheChange(item.niche);
              onLocationChange(item.location);
            }}
            className="btn-ghost text-xs"
          >
            {item.niche} · {item.location}
          </button>
        ))}
      </div>

      <button type="submit" disabled={isLoading} className="btn-primary mt-5 w-full sm:w-auto">
        {isLoading ? "Scrape already running…" : "Find decision makers"}
      </button>
    </form>
  );
}
