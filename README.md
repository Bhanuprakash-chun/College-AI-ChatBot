# College AI Assistant

A full-stack college information chatbot that answers student questions **only from official college documents**. It uses retrieval-augmented generation (RAG): documents are embedded into ChromaDB, questions are matched by semantic similarity, and a local Ollama model writes the answer from the retrieved passages, with citations.

If nothing in the documents is relevant, it says so instead of guessing:

> I couldn't find this information in the available college documents. Please contact the concerned college department.

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, Tailwind CSS v4, React Router, Lucide icons |
| Backend | Python, FastAPI, Pydantic v2, SQLAlchemy 2 |
| Database | MySQL 8 (automatic SQLite fallback), Alembic migrations |
| Vector store | ChromaDB (persistent, cosine space) |
| Embeddings | Sentence Transformers `all-MiniLM-L6-v2` |
| LLM | Ollama, default `llama3.2:3b` |
| Auth | JWT access tokens, bcrypt password hashing, role-based access |
| Ops | Docker Compose, GitHub Actions |

---

## How it works

```text
Ingestion (admin uploads a PDF)
  validate type, size and %PDF signature  ->  safe filename  ->  save
  ->  extract text per page (pypdf)  ->  clean  ->  sentence-aware chunks with overlap
  ->  embed (all-MiniLM-L6-v2)  ->  ChromaDB, with document/page metadata
  ->  status: processing -> ready | failed

Question (student asks)
  follow-up?  fold in the previous question for the search only
  ->  embed  ->  semantic search, top-K  ->  similarity threshold gate
        below threshold  ->  "not found" message, the LLM is never called
        above threshold  ->  grounded prompt  ->  Ollama  ->  answer
  ->  citations built from the retrieved chunks' metadata  ->  saved to chat history
```

**Grounding is enforced in four places**, not just in the prompt:

1. **Similarity gate.** If no chunk reaches `SIMILARITY_THRESHOLD`, the model is never called.
2. **Prompt rules.** The model must use only the supplied passages. It must not infer or fill gaps, and it must say when a specific detail is missing.
3. **Refusal detection.** If the model replies with the not-found sentence, the answer is stored as not grounded and shows no sources.
4. **Citations come from retrieval, not from the model.** The model cannot make the UI show a source that was never retrieved.

If Ollama is down, students still get the relevant document passages, quoted verbatim and clearly labelled. The API does not error.

---

## Quick start (local)

**Prerequisites:** Python 3.11+, Node 20+, and [Ollama](https://ollama.com). MySQL is optional.

### 1. Model

```bash
ollama pull llama3.2:3b
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
copy .env.example .env            # cp on macOS / Linux; then set SECRET_KEY

alembic upgrade head
python scripts/generate_sample_documents.py
python scripts/seed_demo.py       # demo users + indexes the sample PDFs
uvicorn app.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs> (Swagger) and <http://localhost:8000/redoc>.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

In development, Vite proxies `/api/*` to the backend. To use another backend port, set `VITE_BACKEND_URL` in `frontend/.env.local`.

### Demo accounts (created by `seed_demo.py`)

| Role | Email | Password |
|---|---|---|
| Admin | `admin@college.edu` | `Admin@12345` |
| Student | `student@college.edu` | `Student@12345` |

These are **demo-only** credentials. Without the seed script, the first startup creates one admin. It uses `BOOTSTRAP_ADMIN_PASSWORD` if set; otherwise it generates a random password and prints it once to the server log. There is no built-in default credential.

### MySQL

Set `MYSQL_*` (or `DATABASE_URL`) in `backend/.env`. The database is created if missing. If MySQL is unreachable at startup, the app falls back to SQLite, and `/health` and the admin dashboard report it as **Degraded**. Set `DB_ALLOW_SQLITE_FALLBACK=false` to fail instead.

---

## Demo walkthrough

1. Sign in as **admin**. The dashboard shows users, documents, chunks, questions, active users, processing, and failed documents, plus live health for the database, ChromaDB, and Ollama.
2. **Manage documents**: upload `documents/demo-upload/academic_calendar_2025_26.pdf`. It is deliberately not pre-indexed. It appears as **Processing**, then turns **Ready** on its own.
3. Sign out and sign in as **student**.
4. Ask *"When do the odd semester end exams start this year?"* The answer (17–29 November 2025) comes from the document you just uploaded, with **Academic Calendar 2025-26 · p.1** as the source.
5. Follow up with *"And the even semester ones?"* Multi-turn context resolves it to 18–30 May 2026.
6. Ask something off-topic, such as *"Who is the chief minister of the state?"* It is refused and marked **Not found in college documents**.
7. Rate answers 👍/👎, then open **History** to search and reopen conversations.
8. Back as admin, review **Analytics**, **Feedback**, and **Audit logs**. **Reprocess** or **Delete** the calendar and ask again: its answers are gone.

---

## Configuration

All settings are environment variables (see `backend/.env.example`). The key RAG settings:

| Variable | Default | Notes |
|---|---|---|
| `CHUNK_SIZE` | `500` | **Characters**, not words (see below) |
| `CHUNK_OVERLAP` | `100` | Characters carried into the next chunk |
| `TOP_K` | `5` | Chunks retrieved per question |
| `SIMILARITY_THRESHOLD` | `0.30` | Cosine similarity gate, 0 to 1 |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence Transformers model |
| `OLLAMA_MODEL` | `llama3.2:3b` | Any pulled Ollama model |
| `OLLAMA_KEEP_ALIVE` | `30m` | Keeps the model loaded between questions |
| `CHROMA_PATH` | `../chroma_db` | Persistent vector store |
| `MAX_UPLOAD_MB` | `25` | Upload size limit |
| `RATE_LIMIT_LOGIN` / `_REGISTER` / `_CHAT` / `_UPLOAD` | `10/60`, `5/300`, `30/60`, `20/300` | requests / seconds, per client IP |

**Why characters?** `all-MiniLM-L6-v2` truncates input at 256 word-pieces. A 500-*word* chunk would lose about half its text before embedding, and retrieval would quietly suffer. 500 characters is roughly 125 tokens and fits the model's window. Chunks are sentence-aligned; a single over-long sentence is split on word boundaries.

---

## API

| Method | Path | Access |
|---|---|---|
| POST | `/auth/register` · `/auth/login` · `/auth/logout` | public · public · signed in |
| GET | `/auth/me` | signed in |
| POST | `/chat` | signed in |
| GET / POST | `/chat/sessions` | own sessions |
| GET / DELETE | `/chat/sessions/{id}` | own sessions |
| POST | `/feedback` | own answers |
| GET | `/documents` | signed in (ready documents, metadata only) |
| POST | `/admin/documents/upload` | admin |
| GET | `/admin/documents` · `/admin/documents/{id}` | admin |
| DELETE | `/admin/documents/{id}` | admin |
| POST | `/admin/documents/{id}/reprocess` | admin |
| GET / PATCH / DELETE | `/admin/users`, `/admin/users/{id}` | admin |
| GET | `/admin/statistics` · `/admin/analytics` · `/admin/feedback` · `/admin/audit-logs` | admin |
| GET | `/health` | public |

---

## Security

- **Passwords** are hashed with bcrypt (cost 12). Registration requires 8+ characters with a letter and a digit.
- **JWTs** are HS256 with an `exp` claim (60 minutes by default). Tokens are type-checked, and deactivated users are rejected on every request.
- **RBAC** uses a reusable `RequireRole(...)` guard, so adding a role such as `faculty` doesn't change route code. Self-registration always creates students. An admin cannot demote or delete themselves or remove the last admin.
- **Uploads**: extension allow-list, real `%PDF` signature check, and a size limit enforced while reading, so an oversized upload is never fully buffered. Also SHA-256 duplicate detection, sanitised random filenames, and a path-traversal guard. Students never see file paths or processing errors.
- **Rate limiting** on login, register, chat, and upload, with `429` and `Retry-After`. Limits key on the connection address, never on a client-supplied `X-Forwarded-For`. Behind nginx, uvicorn's `--proxy-headers` provides the real address, and nginx overwrites the header rather than appending to it.
- **Errors**: validation errors are field-level without echoing input. Database and unexpected errors return generic messages, and details go only to the server log. Login failures look the same for unknown emails and wrong passwords, in both message and timing: unknown emails still run a bcrypt check.
- **Health endpoint**: `/health` gives anonymous callers only up/down status. Configuration, the database engine, fallback reasons, and model details are returned only with an admin token.
- **Secrets** come from the environment only. Production refuses to start with the placeholder `SECRET_KEY`. `.env` files are git-ignored.
- **Audit log** records sign-ins, failed sign-ins, registrations, uploads, processing results, deletions, reprocessing, user changes, and feedback, with actor and IP.
- **Model output** is rendered as Markdown with raw HTML disabled.

---

## Testing

```bash
cd backend
python -m pytest -q
```

The suite covers auth, JWT and RBAC, chat, relevant and irrelevant questions, no documents, Ollama failure, PDF upload and invalid PDFs, processing failure, delete and reprocess, and database behaviour. Tests run against a real temporary SQLite database and a real ChromaDB collection with the real embedding model. Only Ollama is stubbed, to keep runs fast and deterministic.

End-to-end against the **live** Ollama model and the indexed demo corpus:

```bash
python scripts/verify_rag.py            # in-scope, out-of-scope, and follow-up checks
python scripts/verify_rag.py --no-llm   # simulate Ollama being down
```

Frontend: `npm run lint` and `npm run build`.

---

## Docker

```bash
cp .env.example .env        # set SECRET_KEY, MYSQL_ROOT_PASSWORD, MYSQL_PASSWORD
docker compose up -d --build
```

The stack runs MySQL, Ollama (a one-shot service pulls the model), the backend (runs `alembic upgrade head`, then serves), and nginx serving the built frontend with `/api` proxied. Data persists in named volumes: `mysql_data`, `chroma_data`, `documents_data`, and `ollama_models`. Open <http://localhost:8080>.

Sign in with `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` from `.env`. If you left the password blank, find the generated one in the backend log:

```bash
docker compose logs backend | grep -A3 "BOOTSTRAP ADMIN"
```

To load the sample documents and the demo student into the running stack:

```bash
docker compose exec backend python scripts/generate_sample_documents.py --out /data/documents/samples
docker compose exec backend python scripts/seed_demo.py --source /data/documents/samples
```

The seed script leaves an existing admin untouched, so in Docker the admin keeps its bootstrap password.

---

## Project structure

```text
college-ai-chatbot/
├── backend/
│   ├── app/
│   │   ├── core/        config, security (JWT/bcrypt), RBAC dependencies, rate limiting
│   │   ├── database/    engine + session, MySQL -> SQLite fallback
│   │   ├── models/      User, Document, ChatSession, ChatMessage, Feedback, AuditLog
│   │   ├── schemas/     Pydantic request/response models
│   │   ├── routers/     auth, chat, feedback, documents, admin, health
│   │   ├── services/    ingestion (background), chat, analytics, audit
│   │   ├── rag/         extractor, cleaner, chunker, embedder, vector store,
│   │   │                retriever, prompt, Ollama client, pipeline
│   │   └── utils/       upload validation and safe filenames
│   ├── alembic/         migrations
│   ├── scripts/         sample documents, demo seed, live RAG verification
│   └── tests/
├── frontend/src/
│   ├── pages/           chat, history, documents, profile, auth, admin/*
│   ├── components/      layout, chat message, citations, charts, UI primitives
│   ├── context/         auth, theme, toasts, chat sessions
│   └── lib/             API client, formatters
├── documents/           uploaded files (samples/ and demo-upload/ are generated)
├── chroma_db/           persistent vectors
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Extending

- **More file types**: register a loader in `app/rag/extractor.py`. A TXT loader already exists; enable it by adding `.txt` to `ALLOWED_UPLOAD_EXTENSIONS`. DOCX and HTML follow the same pattern.
- **Celery/Redis**: processing goes through a `TaskQueue` seam in `document_service.py`. Implement `submit()` with Celery and swap it in; routes don't change.
- **Multi-worker rate limiting**: the limiter is in-process. With several workers, back it with Redis.
- **Reranking**: `Retriever.retrieve` returns the top-K with scores. A cross-encoder can re-order them before the threshold check.

## Known limitations

- The 0.30 threshold was tuned on the sample corpus: off-topic questions scored 0.11–0.27 and on-topic questions 0.59–0.80. Re-check both ranges on your real documents; the admin **Analytics** page lists recently unanswered questions to help.
- Follow-up detection uses a word-pattern heuristic to decide whether the previous question is folded into the search. It never finds answers itself, but an unusual phrasing can be misclassified.
- Scanned, image-only PDFs are rejected with a clear message. OCR is not included.
- Logout is client-side (JWTs are stateless). A token stays valid until it expires, so keep the expiry short.
- `llama3.2:3b` on CPU answers in about 3–6 seconds once loaded. Startup warms the model in the background, and the very first load after Ollama starts can take a minute.
- The sample documents are realistic but **fictional**. Replace them with your college's real documents.
