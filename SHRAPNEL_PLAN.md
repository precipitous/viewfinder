# Shrapnel -- Self-Replicating Project Spawner

## What It Is

Shrapnel is a meta-project that ingests YouTube videos (via Viewfinder), learns from them, and then forks itself into fully-scaffolded new projects. You feed it video URLs about a topic, discuss the plan, and it spawns a new repo with everything needed to start building.

Named after the Insecticon Decepticon who creates autonomous clones of himself.

## How It Works

```
1. You open Shrapnel in Claude Code
2. Paste YouTube video URLs about the new project idea
3. Shrapnel calls Viewfinder to ingest them (transcripts + screenshots)
4. You discuss the plan -- what to build, how it differs from competition
5. Shrapnel forks itself into a new project:
   - Creates new directory & git repo under ~/
   - Writes CLAUDE.md with full context from video ingestion + discussion
   - Copies standard scaffolding (plugins, settings, skills, CI/CD)
   - Sets up the web UI framework (left sidebar nav, dark theme)
   - Creates GitHub repo under precipitous org
   - Commits and pushes initial scaffold
6. You open the new project in a fresh Claude Code session and start building
```

## First Use Case: Digital Products (Etsy Google Sheets)

Ingest videos about creating high-earning digital products (extensive Google Sheets), then:
- Research competition on Etsy (what exists, pricing, reviews, gaps)
- Design sheets that are significantly better than what's available
- Build, test, iterate (same workflow as all Precipitous projects)
- List and optimize for Etsy SEO

## Architecture

```
~/shrapnel/
  CLAUDE.md              -- Project instructions, workflow, conventions
  SHRAPNEL.md            -- This plan (the meta-instructions)
  package.json           -- Node.js project (for web UI if needed)
  
  src/
    index.html           -- Left sidebar nav web UI (standard Precipitous layout)
    fork.py              -- Project forking logic
    scaffold/            -- Template files copied to new projects
      CLAUDE.md.template
      .claude/
        settings.local.json
      .github/
        workflows/ci.yml
      
  scripts/
    ingest.sh            -- Wrapper: calls viewfinder to process videos
    fork.sh              -- Creates new project from template
    
  library/               -- Symlink to /home/megatron/viewfinder-library/
```

## Standard Precipitous Workflow (from Decepticons Swarm)

### Development Flow
1. **Opus plans and orchestrates** -- designs the approach, breaks into tasks
2. **Opus spawns subagents** (Sonnet/Haiku) to write code in parallel
3. **Opus reviews** -- runs /code-review on the PR
4. **Opus fixes** anything flagged in review
5. **Commit, PR, merge to main, push & deploy**

### Plugins (from global ~/.claude/settings.json)
All of these are installed globally and will be inherited:
- frontend-design -- Production-grade UI generation
- superpowers -- Enhanced Claude Code capabilities
- context7 -- Library documentation lookup
- code-review -- PR review automation
- code-simplifier -- Code quality
- github -- GitHub integration
- feature-dev -- Feature development workflow
- playwright -- Browser automation/testing
- skill-creator -- Create custom skills
- claude-md-management -- CLAUDE.md management
- ralph-loop -- Iteration loops
- security-guidance -- Security best practices
- commit-commands -- Git commit automation

### Permissions (from lendsight settings.local.json)
Standard set includes:
- All git operations (init, add, commit, push, branch, reset)
- npm/node operations (install, build, lint)
- Vercel deployment
- curl, python3, find, grep, ls, cat, echo
- Supabase CLI
- WebSearch, WebFetch

### Conventions
- Python: 3.10+, ruff for linting, modern type hints
- Node/React: TypeScript strict mode, Vite, Tailwind CSS, ESLint zero-warnings
- No em dashes in any output -- use semicolons or hyphens
- Dark theme UI (GitHub-style: #0d1117 bg, #c9d1d9 text, #58a6ff accent)
- Left sidebar navigation layout
- Git: meaningful commit messages, Co-Authored-By tags
- Deploy: Vercel for web apps, GitHub Actions for CI

## Scaffold Template (what gets copied to new projects)

### CLAUDE.md Template
```markdown
# {PROJECT_NAME} -- {DESCRIPTION}

## Project Overview
{Generated from video ingestion + discussion}

## Architecture
{Generated based on project type}

## Development Commands
{Standard npm/python commands}

## Conventions
- Same as all Precipitous LLC projects
- Python 3.10+, ruff linting, modern type hints (if Python)
- TypeScript strict, Vite, Tailwind (if Node/React)
- No em dashes
- Dark theme, left sidebar nav

## Infrastructure Context
Part of the Precipitous LLC / Decepticons ecosystem:
- **Nemesis**: Development workstation (RTX 3090, Ollama for local LLM)
- **Soundwave**: Ubuntu server at 192.168.2.111 (Mattermost, nginx)
- **Viewfinder**: YouTube video ingestion at 192.168.2.229:8080

## Video Sources
{Links to ingested videos with key takeaways}
```

### .claude/settings.local.json Template
```json
{
  "permissions": {
    "allow": [
      "Bash(git:*)", "Bash(npm:*)", "Bash(npx:*)",
      "Bash(node:*)", "Bash(python3:*)", "Bash(pip:*)",
      "Bash(curl:*)", "Bash(ls:*)", "Bash(cat:*)",
      "Bash(find:*)", "Bash(grep:*)", "Bash(echo:*)",
      "Bash(mkdir:*)", "Bash(source:*)",
      "Bash(ruff:*)", "Bash(pytest:*)",
      "Bash(vercel:*)",
      "WebSearch", "WebFetch(domain:github.com)"
    ]
  }
}
```

## Viewfinder Integration

Shrapnel calls Viewfinder's API or CLI to process videos:

```bash
# Via CLI (whisper-only to avoid YouTube rate limits)
viewfinder VIDEO_URL --whisper-only --transcript-only --format json \
  --output-dir ~/shrapnel/library/

# Via API
curl -X POST http://192.168.2.229:8080/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"url": "VIDEO_URL", "whisper_only": true, "transcript_only": true}'
```

The transcripts + screenshots land in the viewfinder library and are accessible to any Claude session.

## Fork Process (step by step)

When user says "fork this into a new project called X":

1. **Create directory**: `mkdir -p ~/X`
2. **Initialize git**: `git init`, set up .gitignore
3. **Copy scaffold**:
   - CLAUDE.md (populated with video context + discussion notes)
   - .claude/settings.local.json (standard permissions)
   - package.json or pyproject.toml (based on project type)
   - src/ skeleton with standard UI layout
4. **Create GitHub repo**: `gh repo create precipitous/X --private`
5. **Initial commit and push**
6. **Print instructions**: "Open ~/X in a new Claude Code session to begin"

## Web UI (Standard Left Sidebar Layout)

If the project needs a web UI, scaffold includes:

```
src/
  index.html          -- Single-page app shell
  styles.css          -- Dark theme, sidebar layout
  app.js              -- Router, tab switching
```

Same dark theme as Viewfinder (and all Precipitous projects):
- Background: #0d1117
- Surface: #161b22
- Border: #30363d
- Text: #c9d1d9
- Accent: #58a6ff
- Green: #238636

Left sidebar with nav items, main content area on right.

## Phase 1: Build Shrapnel (the spawner)

- [ ] Create ~/shrapnel repo with CLAUDE.md
- [ ] Build fork.py -- project scaffolding logic
- [ ] Build ingest.sh -- viewfinder wrapper for video ingestion
- [ ] Create scaffold templates (CLAUDE.md, settings, .gitignore, etc.)
- [ ] Test: fork a dummy project, verify everything is set up correctly
- [ ] Add web UI (left sidebar) for managing spawned projects

## Phase 2: First Spawn -- Etsy Digital Products

- [ ] Ingest YouTube videos about high-earning Etsy digital products
- [ ] Research competition on Etsy (Google Sheets specifically)
- [ ] Define what "better" looks like (more features, better design, automation)
- [ ] Fork Shrapnel into the new project
- [ ] Build the Google Sheets product(s)
- [ ] Test extensively
- [ ] List on Etsy with optimized SEO

## Future Spawns

Each new project idea follows the same pattern:
1. Find YouTube videos about the topic
2. Feed them to Shrapnel via Viewfinder
3. Discuss and plan
4. Fork into a new project
5. Build in the new project's own Claude Code session
