"use client";

import { useEffect, useRef, useState } from "react";
import { filterNicheOptions, NICHE_OPTIONS } from "@/lib/niche-options";

interface NicheInputProps {
  id: string;
  value: string;
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  onChange: (value: string) => void;
}

/**
 * Niche field with a dropdown of popular niches and free-text custom input.
 */
export function NicheInput({
  id,
  value,
  disabled,
  required,
  placeholder,
  onChange,
}: NicheInputProps) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setSuggestions(filterNicheOptions(value));
  }, [value]);

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

  function selectSuggestion(niche: string) {
    onChange(niche);
    setIsOpen(false);
    setHighlighted(-1);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen || suggestions.length === 0) {
      if (event.key === "ArrowDown" && suggestions.length > 0) {
        setIsOpen(true);
      }
      return;
    }

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

  const showCustomHint =
    value.trim().length > 0 &&
    !NICHE_OPTIONS.some(
      (item) => item.toLowerCase() === value.trim().toLowerCase(),
    );

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
        onFocus={() => setIsOpen(true)}
        className="field-input"
      />

      {isOpen && suggestions.length > 0 ? (
        <ul
          id={`${id}-suggestions`}
          role="listbox"
          className="panel absolute left-0 right-0 top-full z-30 mt-1 max-h-64 overflow-y-auto shadow-lg"
        >
          {suggestions.map((niche, index) => {
            const isCustom =
              showCustomHint &&
              niche.toLowerCase() === value.trim().toLowerCase();

            return (
              <li
                key={`${niche}-${index}`}
                role="option"
                aria-selected={index === highlighted}
              >
                <button
                  type="button"
                  onClick={() => selectSuggestion(niche)}
                  onMouseEnter={() => setHighlighted(index)}
                  className={`block w-full px-3 py-2.5 text-left text-sm ${
                    index === highlighted ? "bg-paper text-ink" : "text-ink/75"
                  }`}
                >
                  <span className="font-medium text-ink">{niche}</span>
                  {isCustom ? (
                    <span className="mt-0.5 block text-xs text-ink/50">
                      Use custom niche
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
