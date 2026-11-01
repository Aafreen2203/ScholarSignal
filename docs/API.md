# API contracts (v1)

Base path: `/api/v1`. OpenAPI is served at `/api/docs`. Browser calls use the
same-origin Next.js `/api/*` proxy, which forwards cookies, JSON bodies, status
codes, and `Retry-After` headers to FastAPI.

## Authentication

| Method | Endpoint | Request | Response / behavior |
| --- | --- | --- | --- |
| POST | `/auth/register` | `{email, password, display_name}` | 201 user summary and HttpOnly session cookie; 409 duplicate; 422 invalid; 429 limited; 503 Redis unavailable |
| POST | `/auth/login` | `{email, password}` | 200 user summary and cookie; 401 generic credential error; 429 limited; 503 Redis unavailable |
| POST | `/auth/logout` | none | 204 and clears session cookie |
| GET | `/auth/me` | session cookie | 200 user summary; 401 absent, invalid, or expired session |

Passwords and hashes are not returned. Workspace endpoints require the session
cookie and scope every row to the authenticated owner.

## Search and publication records

| Method | Endpoint | Request / behavior |
| --- | --- | --- |
| GET | `/search` | `q` required (1–500 chars); `method=lexical\|semantic\|hybrid`; `page` (1–100); `per_page` (1–50); `sort_by=relevance\|date\|citations`; optional `year_from`, `year_to`, `author`, and `topic` filters. Returns persisted publication metadata, score, per-result explanation, method explanation, page counts, and `results_capped`. |
| GET | `/publications/{id}` | Public publication detail from the local database, including provenance, venue, available metadata, and up to 50 source-provided OpenAlex reference IDs. Authenticated views update that user's recent-view row. |
| GET | `/publications/{id}/related` | Up to 20 nearest records by similarity to an already stored local embedding; returns 409 if the record has no current embedding. No external model/API call. |
| GET | `/search/history` | Authenticated only; most recent searches for the current account, up to 100. The service retains at most 200 per user. |

Lexical retrieval uses PostgreSQL English full-text ranking across titles and
abstracts. Semantic retrieval embeds the query locally with FastEmbed and uses
pgvector cosine distance. Hybrid retrieval uses reciprocal-rank fusion (RRF)
over up to 1,000 candidates from each method. `results_capped=true` indicates
the bounded candidate set is truncated; in that case the returned total is the
available candidate set, not a corpus-wide count. A clean test database has no
OpenAlex rows, so results may be empty.

Search results include `openalex_id`, title, abstract, authors, publication
date, DOI, topics/concepts, citation count (nullable when absent), retrieval
score, and explanation. Missing source fields remain null rather than being
filled with synthetic values.

## Authenticated workspace

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET / POST | `/workspace/saved` | List saved papers / idempotently save `{publication_id}` |
| DELETE | `/workspace/saved/{publication_id}` | Remove the current user's bookmark |
| GET / POST | `/workspace/collections` | List the user's collections / create `{name, description?}` |
| DELETE | `/workspace/collections/{id}` | Delete an owned collection; cascades its memberships |
| GET / POST | `/workspace/collections/{id}/publications` | List / idempotently add `{publication_id}` to an owned collection |
| DELETE | `/workspace/collections/{id}/publications/{publication_id}` | Remove an item from an owned collection |
| GET / POST | `/workspace/notes` | List / create `{title, body, publication_id?}` private notes |
| PATCH / DELETE | `/workspace/notes/{id}` | Update or delete an owned note; non-owned IDs return 404 |
| GET | `/workspace/recent` | Current user's recently viewed publications |

Collection and note operations use database constraints and ownership predicates;
they do not reveal whether another user's private resource exists. Publication
IDs refer to records already present in the local library.

## Health and operator commands

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/health/live` | Process liveness |
| GET | `/health/ready` | 200 only when PostgreSQL and Redis are reachable; otherwise 503 |

OpenAlex ingestion and embedding generation are operator CLI actions, not
public API routes. Use the usage/budget ledger and project ceiling before any
live OpenAlex operation; never resume a cursor implicitly. See
[`DATA_PIPELINE.md`](DATA_PIPELINE.md).
