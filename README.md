COMPREHENSIVE PROMPT FOR BUILDING NAUKRI JOB AGENT
Project Overview
Build a robust, production-ready Python agent that automates job applications on Naukri.com using Playwright. The agent authenticates via .env credentials, searches for DevOps/Cloud roles with 3 years experience in preferred locations, sorts by date, matches skills from resume/profile against job requirements using weighted category-based scoring, and handles 3 distinct apply scenarios with a live terminal UI.
Core Architecture
job-agent/
├── run_agent.py          # Main entry point (CLI args, UI setup)
├── login.py              # Naukri authentication (saves session.json)
├── .env                  # NAUKRI_EMAIL, NAUKRI_PASSWORD
├── user_profile.yaml     # Roles, locations, skills, thresholds, Q&A
├── pyproject.toml        # Dependencies
├── src/
│   ├── __init__.py
│   ├── auth.py           # NaukriAuth: login, session validation
│   ├── search.py         # JobSearch: search, filter, extract cards
│   ├── apply_new_sync.py # JobApplier: main pipeline, 3 scenarios
│   ├── matcher_v2.py     # Weighted skill matching (must-have vs nice-to-have)
│   ├── resume.py         # PDF parsing → structured Resume model
│   ├── ui.py             # LiveJobTable: Rich-based real-time table
│   ├── data_collector.py # JobDataCollector: JSON/Excel output
│   ├── chatbot_answerer.py # Chatbot Q&A handling (sync + async)
│   └── llm_extractor.py  # LLM-based skill extraction from resume
Detailed Requirements
1. Authentication Flow
- Run: python3 login.py first (one-time setup)
- Reads NAUKRI_EMAIL, NAUKRI_PASSWORD from .env
- Uses Playwright + Stealth to login at https://www.naukri.com/nlogin/login
- Saves cookies to session.json
- Validates session on subsequent runs
2. Job Search Configuration (from user_profile.yaml)
strict_roles:           # Search keywords (e.g., "DevOps Engineer", "AWS Cloud Engineer")
preferred_locations:    # ["Bengaluru", "Hyderabad"]
experience: 3           # Hardcoded in search URL: ?experience=3
max_days_old: 1         # Only jobs posted within 1 day
min_skill_match: 80     # Match threshold percentage
headless_mode: false    # Visible browser
max_parallel_jobs: 3    # Parallel processing limit
3. Search & Filter Logic (src/search.py)
- For each role in strict_roles:
- Navigate: https://www.naukri.com/{role}-jobs?experience=3
- Apply location filter from preferred_locations (multi-select)
- Sort by Date (newest first) - CRITICAL: verify sort worked by checking first job shows "Just now"/"Hours ago"
- Extract 20 job cards per page with: title, company, location, experience, posted_date, URL
- Use JSON-LD structured data as primary, DOM selectors as fallback
4. Skill Matching Algorithm (src/matcher_v2.py)
Weighted Category-Based Scoring for >80% accuracy:
Category	Weight	Required	Skills
cloud_providers	1.5	✅	aws, azure, gcp, eks, aks, gke, lambda, ec2, rds, s3, iam, vpc
container_orchestration	1.5	✅	kubernetes, helm, argocd, flux, istio, ingress
ci_cd	1.3	✅	jenkins, github actions, gitlab ci, azure devops
gitops	1.3	✅	argocd, flux, helmfile, kustomize
iac	1.3	✅	terraform, terragrunt, cloudformation, ansible
monitoring_observability	1.2	❌	prometheus, grafana, loki, tempo, datadog, cloudwatch
security	1.2	❌	trivy, vault, sonarqube, rbac, istio
containerization	1.2	✅	docker, containerd, podman, buildkit
scripting	1.1	❌	python, go, bash, powershell, boto3
databases	1.0	❌	postgresql, redis, dynamodb, mongodb
networking	1.0	❌	vpc, alb, nlb, route53, cloudfront, vpn
Matching Logic:
- Normalize skills via SKILL_ALIASES (e.g., "k8s" → "kubernetes", "ci cd" → "ci/cd")
- Calculate: match_pct = (matched_weight / total_weight) * 100
- Hard fail: If any required=True category scores < 50%, force match < 80%
- Returns: (should_apply: bool, match_pct: float, matched: List[str], missing: List[str])
5. Must-Have vs Good-to-Have Extraction
From job description, categorize extracted skills:
- Must Have = skills from required=True categories present in JD
- Good to Have = skills from required=False categories present in JD
- Store both in job data for UI table display
6. Job Detail Processing (New Tab)
For each job card:
1. Click link → opens in new tab (context.expect_page())
2. Wait for JD selectors: [class*='jd-container'], .job-desc, .JDContent
3. Extract full JD text (limit 5000 chars)
4. Run extract_skills_from_text(jd_text) → job_skills
5. Get resume_skills from user_profile.yaml → optimized_skills (primary) + resume parsed skills (fallback)
6. Run should_apply(resume_skills, jd_text, threshold=80)
7. If match ≥ 80% → proceed to apply; else skip with reason
7. Three Apply Scenarios (click_apply method)
Scenario	Detection	Action
1. Direct Apply	Redirect + success toast ("Applied", "Success") OR URL contains "applied"	Mark applied, record in collector
2. Chatbot Dialog	Sidebar/overlay appears with questions (radio + text inputs)	Process all questions via ChatbotAnswerer, click "Save" after each, verify "Applied" at end
3. Company Site	Button text "Apply on company site" opens new tab	Capture: title, company, exp, location, must_have, good_to_have, naukri_url, company_site_url → save to ManualApplyCollector for Excel export
Chatbot Answering Logic:
- Priority 1: Profile Q&A from user_profile.yaml (fuzzy match >80%)
- Priority 2: Yes/No radio buttons → logic for counter-offer (No), relocate (Yes), notice period (No)
- Priority 3: "Write NA/N/A" text inputs → answer "NA"
- Priority 4: Skill-specific experience → lookup in skill_inventory (resume + profile), answer "3 years" or "0 years"
- Priority 5: Common patterns (notice period, CTC, total experience, current company)
- Priority 6: Interactive fallback (8s for manual input, saves to profile)
8. Live Processing UI (src/ui.py - Rich Live Table)
Columns:
Column	Source
Title	Job card title
Company	Job card company
Experience	Job card experience
Must Have Skills	Matched required-category skills from JD
Good to Have Skills	Matched optional-category skills from JD
Status	Spinner + state (Fetching → Analyzing XX% → Applying → ✓ Applied / → Company Site / ✗ Skipped: reason / ⚠ Error)
Summary Bar: ✓ Applied: N | ✗ Skipped: N | ⚠ Errors: N | 📋 Total: X/Y
Real-time updates via Live with refresh_per_second=10, spinner animation on active rows.
9. Data Persistence
- Daily JSON: output/day_N.json - all processed jobs with full details
- Manual Apply Excel: output/manual_apply_YYYYMMDD_HHMMSS.xlsx - company site jobs
- Session: session.json - Naukri cookies
10. Key Configurations (from user_profile.yaml)
apply_threshold: 0.8      # 80% match threshold
max_days_old: 1           # Ignore jobs older than 1 day
min_skill_match: 80       # Same as apply_threshold
check_all_jobs: true      # Don't filter by title relevance
job_delay_seconds: 2      # Rate limiting
notice_period_months: 3   # For chatbot answers
current_ctc_lpa: 6.0
expected_ctc_lpa: 12.0
Critical Implementation Details
Robust Selectors (Naukri DOM changes frequently)
# Job cards - try multiple
"[data-job-id]", ".jobTuple", ".job-card", "article.jobTuple", ".srp-jobtuple-wrapper"

# Sort by date
"#filter-sort" → click → "a[data-id='filter-sort-f']" or "[data-filter-id='sort'] *:has-text('Date')"

# Apply button
"button:has-text('Apply on company site')", "#apply-button", "button:has-text('Apply')"

# Chatbot container
"[class*='chatbot']", "[class*='apply-sidebar']", "aside[class*='question']", "[role='dialog'][class*='apply']"

# JD extraction
"[class*='jd-container']", "[class*='job-desc']", ".JDContent", ".jobDescription"
Error Handling & Retry Logic
- Every click: 3 retries with 2s delay
- Page navigation: 60-90s timeouts
- Stale element recovery: re-query selectors
- Always close job detail tabs in finally block
- Dismiss chatbot overlays before clicks (Escape key + overlay selectors)
Parallel Processing
- ThreadPoolExecutor with max_workers=max_parallel_jobs
- Each worker gets own browser context + cookies
- Thread-safe collectors with threading.Lock
CLI Interface (run_agent.py)
python3 run_agent.py [options]
  --max-jobs N        # Max jobs per role (default: 5)
  --threshold N       # Skill match % (default: 80)
  --max-days N        # Max job age (default: 1)
  --search-only       # Only search, don't apply
  --dry-run           # Show what would be applied
  --parallel N        # Parallel jobs (default: 3)
  --no-ui             # Disable live UI, simple output
Dependencies (pyproject.toml)
dependencies = [
    "playwright>=1.40",
    "playwright-stealth>=1.0",
    "python-dotenv>=1.0",
    "rich>=13.0",
    "openai>=1.0",        # For LLM skill extraction
    "rapidfuzz>=3.0",     # Fuzzy matching
    "tiktoken>=0.7",      # Token counting
    "pandas>=2.0",        # Excel export (optional)
    "pdfplumber>=0.10",   # Resume PDF parsing
    "pyyaml>=6.0",        # Config
    "pydantic>=2.0",      # Data models
]
Validation Checklist for Implementation
- Login saves valid session.json
- Search applies location filter + sort by date (verified)
- Job cards extracted with all fields (title, company, location, exp, posted, url)
- Jobs >1 day old are skipped
- JD extracted from new tab, skills categorized as must-have/good-to-have
- Weighted matching produces >80% for qualified DevOps roles
- Scenario 1: Direct apply detected via toast/redirect
- Scenario 2: Chatbot questions answered, "Save" clicked, final "Applied" verified
- Scenario 3: Company site jobs captured to Excel with all required fields
- Live UI table updates in real-time with spinners
- Daily JSON + manual apply Excel generated
- Parallel processing works without session conflicts
Architecture Principles
1. Separation of concerns: Search, Match, Apply, UI, Data are independent modules
2. Defensive coding: Retry logic, stale element recovery, timeout handling
3. Config-driven: All thresholds, roles, locations in user_profile.yaml
4. Observable: Live UI + structured logs + debug dumps
5. Extensible: New apply scenarios, new job boards via provider pattern
