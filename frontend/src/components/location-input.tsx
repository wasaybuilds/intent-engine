"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface LocationInputProps {
  id: string;
  value: string;
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  onChange: (value: string) => void;
}

interface PlaceSuggestion {
  /** Display label, e.g. "Austin, Texas, United States" */
  label: string;
  /** Short value written into the field, e.g. "Austin TX" */
  value: string;
}

/** Photon (OpenStreetMap) — free geocoding autocomplete, no API key. */
const PHOTON_URL = "https://photon.komoot.io/api/";

const DEBOUNCE_MS = 300;

/** US state names → 2-letter codes so selections match scrape-friendly format. */
const US_STATE_CODES: Record<string, string> = {
  Alabama: "AL", Alaska: "AK", Arizona: "AZ", Arkansas: "AR", California: "CA",
  Colorado: "CO", Connecticut: "CT", Delaware: "DE", Florida: "FL", Georgia: "GA",
  Hawaii: "HI", Idaho: "ID", Illinois: "IL", Indiana: "IN", Iowa: "IA",
  Kansas: "KS", Kentucky: "KY", Louisiana: "LA", Maine: "ME", Maryland: "MD",
  Massachusetts: "MA", Michigan: "MI", Minnesota: "MN", Mississippi: "MS",
  Missouri: "MO", Montana: "MT", Nebraska: "NE", Nevada: "NV",
  "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
  "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", Ohio: "OH",
  Oklahoma: "OK", Oregon: "OR", Pennsylvania: "PA", "Rhode Island": "RI",
  "South Carolina": "SC", "South Dakota": "SD", Tennessee: "TN", Texas: "TX",
  Utah: "UT", Vermont: "VT", Virginia: "VA", Washington: "WA",
  "West Virginia": "WV", Wisconsin: "WI", Wyoming: "WY",
};

/**
 * Map a Photon feature to a suggestion with a scrape-friendly short value.
 */
function toSuggestion(feature: {
  properties?: {
    name?: string;
    city?: string;
    state?: string;
    country?: string;
    countrycode?: string;
  };
}): PlaceSuggestion | null {
  const props = feature.properties ?? {};
  const name = props.name || props.city;
  if (!name) return null;

  const parts = [name, props.state, props.country].filter(Boolean);
  const label = parts.join(", ");

  // "Austin TX" for US cities; "London UK"-style elsewhere
  let short = name;
  if (props.countrycode?.toUpperCase() === "US" && props.state) {
    short = `${name} ${US_STATE_CODES[props.state] ?? props.state}`;
  } else if (props.country) {
    short = `${name}, ${props.country}`;
  }

  return { label, value: short };
}

/**
 * Location field with type-ahead city suggestions (OpenStreetMap/Photon).
 */
export function LocationInput({
  id,
  value,
  disabled,
  required,
  placeholder,
  onChange,
}: LocationInputProps) {
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const skipNextFetch = useRef(false);

  const fetchSuggestions = useCallback(async (query: string) => {
    try {
      const url = `${PHOTON_URL}?q=${encodeURIComponent(query)}&limit=6&layer=city&layer=state`;
      const response = await fetch(url);
      if (!response.ok) return;

      const data = await response.json();
      const seen = new Set<string>();
      const results: PlaceSuggestion[] = [];

      for (const feature of data.features ?? []) {
        const suggestion = toSuggestion(feature);
        if (suggestion && !seen.has(suggestion.label)) {
          seen.add(suggestion.label);
          results.push(suggestion);
        }
      }

      setSuggestions(results);
      setIsOpen(results.length > 0);
      setHighlighted(-1);
    } catch {
      // Autocomplete is best-effort; typing manually still works
      setSuggestions([]);
      setIsOpen(false);
    }
  }, []);

  useEffect(() => {
    if (skipNextFetch.current) {
      skipNextFetch.current = false;
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);

    const query = value.trim();
    if (query.length < 2) {
      setSuggestions([]);
      setIsOpen(false);
      return;
    }

    debounceRef.current = setTimeout(() => fetchSuggestions(query), DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value, fetchSuggestions]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function selectSuggestion(suggestion: PlaceSuggestion) {
    skipNextFetch.current = true;
    onChange(suggestion.value);
    setIsOpen(false);
    setSuggestions([]);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen || suggestions.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((prev) => (prev + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((prev) => (prev <= 0 ? suggestions.length - 1 : prev - 1));
    } else if (event.key === "Enter" && highlighted >= 0) {
      event.preventDefault();
      selectSuggestion(suggestions[highlighted]);
    } else if (event.key === "Escape") {
      setIsOpen(false);
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        id={id}
        type="text"
        role="combobox"
        aria-controls={`${id}-suggestions`}
        aria-expanded={isOpen}
        aria-autocomplete="list"
        autoComplete="off"
        required={required}
        disabled={disabled}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (suggestions.length > 0) setIsOpen(true);
        }}
        className="field-input"
      />

      {isOpen ? (
        <ul
          id={`${id}-suggestions`}
          role="listbox"
          className="panel absolute left-0 right-0 top-full z-30 mt-1 max-h-64 overflow-y-auto shadow-lg"
        >
          {suggestions.map((suggestion, index) => (
            <li key={suggestion.label} role="option" aria-selected={index === highlighted}>
              <button
                type="button"
                onClick={() => selectSuggestion(suggestion)}
                onMouseEnter={() => setHighlighted(index)}
                className={`block w-full px-3 py-2.5 text-left text-sm ${
                  index === highlighted ? "bg-paper text-ink" : "text-ink/75"
                }`}
              >
                <span className="font-medium text-ink">{suggestion.value}</span>
                <span className="mt-0.5 block text-xs text-ink/50">
                  {suggestion.label}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
