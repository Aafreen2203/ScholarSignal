export function doiUrl(value: string): string {
  const doi = value.trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "");
  return `https://doi.org/${encodeURIComponent(doi)}`;
}

export function openAlexUrl(value: string): string {
  const id = value.trim().replace(/^https?:\/\/openalex\.org\//i, "");
  return `https://openalex.org/${encodeURIComponent(id)}`;
}
