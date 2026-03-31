/** Popular B2B niches shown in the niche dropdown (users can still type any custom value). */
export const NICHE_OPTIONS: string[] = [
  "dentists",
  "orthodontists",
  "chiropractors",
  "HVAC companies",
  "plumbers",
  "electricians",
  "roofing contractors",
  "landscaping companies",
  "pest control companies",
  "personal injury lawyers",
  "family law attorneys",
  "accountants",
  "bookkeepers",
  "marketing agencies",
  "web design agencies",
  "real estate agents",
  "property management companies",
  "auto repair shops",
  "car dealerships",
  "gyms and fitness studios",
  "med spas",
  "veterinarians",
  "restaurants",
  "coffee shops",
  "hotels",
  "commercial cleaning companies",
  "IT managed service providers",
  "cybersecurity consultants",
  "staffing agencies",
  "recruitment firms",
  "insurance agencies",
  "mortgage brokers",
  "financial advisors",
  "wealth management firms",
  "SaaS companies",
  "e-commerce brands",
  "manufacturing companies",
  "logistics companies",
  "construction companies",
  "architecture firms",
  "interior design studios",
];

/**
 * Filter niche suggestions by query (case-insensitive substring match).
 *
 * @param query - Current input text
 * @param limit - Max suggestions to return
 */
export function filterNicheOptions(query: string, limit = 8): string[] {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) return NICHE_OPTIONS.slice(0, limit);

  const matches = NICHE_OPTIONS.filter((niche) =>
    niche.toLowerCase().includes(trimmed),
  );

  // If the typed value is not in the list, offer it as a custom option
  const exactMatch = NICHE_OPTIONS.some(
    (niche) => niche.toLowerCase() === trimmed,
  );
  if (!exactMatch && trimmed.length > 0) {
    return [query.trim(), ...matches].slice(0, limit);
  }

  return matches.slice(0, limit);
}
