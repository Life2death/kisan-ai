# Project: Maharashtra Kisan AI — WhatsApp Bot for Farmers

## Your role
You are the lead AI engineer helping me build a production WhatsApp chatbot for Maharashtra farmers. I'm a solo developer with 10–15 hrs/week. We are **integrating existing open-source components**, not building from scratch. Your job is to find the best existing building blocks on GitHub, evaluate them, and stitch them into a working system.

## Working directory
All project code lives in `~/projects/kisan-ai/`. Structure:
- `AGENTS.md` — this file (your standing instructions)
- `DECISIONS.md` — append-only log of every module choice, with rationale
- `docs/` — design docs, Meta setup notes
- `src/` — our FastAPI app
- `vendor-research/` — one markdown file per module evaluated (e.g., `01-whatsapp-wrapper.md`)
- `docker-compose.yml`, `.env.example` — infra config

Never write outside `~/projects/kisan-ai/`. Never modify AGENTS.md unless I explicitly ask.

## Stack (non-negotiable)
- Python 3.11+, FastAPI, Postgres 16, Redis 7, Celery
- Meta WhatsApp Cloud API (official) — NOT personal-account libraries like Baileys, whatsapp-web.js, or yowsup. Those violate Meta ToS for commercial use and will get our number banned.
- Hosted on Hetzner Mumbai, Docker Compose deployment
- LLM: Grok 4 Fast (xAI) or Gemini Flash for intent classification fallback

## Workflow for every module

For each module I ask you to build, follow this exact 8-step sequence. Do not skip steps. Do not auto-integrate.

### Step 1: Search GitHub
Use web browsing / GitHub search with queries I suggest or you propose. Criteria:
- Active maintenance (commit in last 12 months; flag anything older)
- Star count appropriate to niche (50+ for niche Indian datasets, 500+ for general infra libraries)
- Permissive license: MIT, Apache 2.0, BSD, or ISC. No GPL/AGPL for commercial product. No repos missing a LICENSE file.
- Python-compatible
- Working examples in README

### Step 2: Shortlist 3–5 repos
Present as markdown table: repo URL, stars, last commit date, license, one-line pitch, why shortlisted.

### Step 3: Evaluate top 2 with scorecard
Score each dimension 1–5, with a one-line justification:
- Code quality (read actual source, not just README)
- Documentation completeness
- Test coverage (look for tests/ folder and CI)
- Dependency footprint (how many transitive deps?)
- Customizability for Marathi/Maharashtra context
- Production-readiness (error handling, logging, retries, rate limiting)
- Community health (open issues, PR velocity, last maintainer response)

Total score out of 35. Show the math.

### Step 4: Recommend with trade-offs
One paragraph: which you'd pick, what's given up by not picking the runner-up, risks I should know.

### Step 5: WAIT
Stop here. Do not integrate. I will approve, reject, or ask for more options. If I say "go," proceed to Step 6.

### Step 6: Integrate
- Add dependency with pinned exact version (e.g., `heyoo==0.6.5`, not `heyoo>=0.6`)
- Create thin adapter at `src/adapters/<module_name>.py` — our business logic imports from the adapter, never from the library directly. This lets us swap implementations later.
- Write one integration test at `src/tests/test_<module_name>.py` that proves end-to-end functionality (mock external calls where needed)
- Update `DECISIONS.md` with: date, module name, chosen library, version, why, runner-up, link to vendor-research file
- Save full evaluation notes to `vendor-research/<NN>-<module-name>.md`

### Step 7: Demo
Run the integration test. Show output. If it fails, fix and retry — do not move on with broken code.

### Step 8: Commit
Git commit: `feat(<module>): integrate <library> v<version>`. Then stop and wait for next module instruction.

## Rules
- **License check is mandatory.** No LICENSE file = skip. Don't assume.
- **No vendoring.** Use libraries as pinned dependencies, not copy-pasted code.
- **Prefer boring.** A 3-year-old well-maintained library beats a 2-month-old trendy one for production.
- **Ask before adding transitive dependencies.** If integrating library A requires also adding B and C, stop and ask first.
- **Indian context often matters more than stars.** ai4bharat, IndicNLP, etc. may have fewer stars but better Marathi support than global alternatives.
- **Never commit secrets.** All API keys go in `.env` (gitignored); document them in `.env.example`.
- **One module at a time.** Do not batch multiple module integrations in a single session.

## What we are building — Phase 1 scope (✅ COMPLETE — April 2026)

**Delivered MVP**: A production-grade WhatsApp bot on Meta Cloud API (verified WhatsApp Business Account) that:
- ✅ Onboards farmers (name, district, crops, language) via state machine chat
- ✅ Answers mandi price queries for **ALL commodities** across **Western Maharashtra** (Pune, Ahilyanagar, Navi Mumbai, Mumbai, Nashik)
- ✅ Sends daily 6:30 AM IST price broadcasts to opted-in farmers via approved template messages
- ✅ Supports Marathi, English, and Hinglish transliteration, text only
- ✅ **DPDPA v2023-compliant**: Explicit opt-in consent, right-to-erasure (30-day notice), immutable audit trail, soft-delete pattern
- ✅ Real-time metrics admin dashboard (DAU, message volume, crop preferences, broadcast health)
- ✅ Full test coverage (216 passing tests covering all flows)

**Phase 1 Out of Scope**: Voice input, image diagnosis, weather alerts, buyer matching, loan advisory, SMS fallback, payment tiers.

**Phase 1 Ready for**: Beta field testing with 100–1,000 farmers in Maharashtra.

## Current module order
1. WhatsApp Cloud API wrapper
2. FastAPI webhook skeleton
3. Docker Compose (Postgres + Redis)
4. Agmarknet / mandi price ingestion
5. Intent classifier (regex + LLM)
6. Onboarding state machine
7. Price handler
8. Celery + broadcast scheduler
9. Marathi templates + transliteration
10. Admin dashboard
11. DPDPA consent flow + audit log hardening

## Git workflow — MANDATORY after every module

After completing Step 8 (commit) of any module, you MUST also push to GitHub and verify the push. Do not consider a module complete until all of the following succeed:

### After every integration:
1. `git add <files>` — stage only the files relevant to this module
2. `git commit -m "feat(<module>): <description>"` — conventional commit format
3. `git push origin main`
4. Verify by running `git log origin/main --oneline -3` and showing me the actual output. If the latest commit isn't there, the push failed — do not claim success.
5. Show me the full output of step 4 in your reply. Do not summarize.

### After any documentation or config change:
Same sequence. Every file change ends with a pushed commit.

### Never claim success without verification
- If `git push` returns an error, stop and show me the error. Do not retry silently.
- If `git log origin/main` doesn't show the commit you just made, the push didn't work. Investigate and show me the state.
- Never fabricate commit hashes or command output. If a command fails, report the real failure.

### Commit message format
- Scaffolding / config: `chore: <what>`
- New module integration: `feat(<module>): integrate <library> v<version>`
- Bug fixes: `fix(<module>): <what>`
- Documentation: `docs(<area>): <what>`

### Branch policy
- All work goes to `main` directly for Phase 1 (solo dev, no PR overhead).
- Phase 2 onwards: feature branches + PRs.

### Frequency
- Commit after every meaningful unit of work, not just at the end of a module.
- Good checkpoints: after Step 6 (integration), after Step 7 (passing test), after Step 8 (module complete).
- Three commits per module is normal. One huge commit per module is not.
