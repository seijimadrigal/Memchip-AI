# MemChip Dashboard Redesign — Mem0 Style

## Reference: Mem0 Dashboard (app.mem0.ai)

### Layout Structure
- **Sidebar** (left, ~180px, collapsible):
  - Logo + org name at top
  - Grouped sections with labels: ACTIVITY, ACCOUNT
  - Active page highlighted with bg color
  - Bottom: plan usage bar + icon links (discord, status, support)
  
- **Top bar**: Date range picker (All Time / 1d / 7d / 30d) + Filters + Refresh buttons

### Pages to Implement (matching Mem0 features we have)

#### 1. Dashboard (/)
- **4 stat cards** in a row (flat, no rounded corners, minimal):
  - Total Memories (count)
  - API Requests (count) 
  - Search Events (count)
  - Add Events (count)
- **2 charts** side by side:
  - Requests over time (area chart, green)
  - Entities over time (line chart, blue)
  - Toggle: "View Breakdown" switch
- **"Explore the Platform"** section with card links (skip this — Mem0-specific)

#### 2. Memories (/memories)
- **Tab bar**: Overview | triple | summary | profile | temporal (our types, like Mem0's categories)
- **Table columns**: Time | Agent | Memory Content | Type | Categories/Tags | Action (delete icon)
- **Date range picker** top right
- **Filters + Refresh** buttons
- Relative timestamps ("2d ago", "3d ago")
- Click row to expand/view details

#### 3. Entities → Agents (/agents) 
- **Tab bar**: USER | AGENT (Mem0 has USER/RUN/AGENT/APP)
- **Table**: Entity name | Memory Count | Last Updated | Action (delete)
- Show our agents: lyn, luna
- Click to drill into agent's memories

#### 4. Requests → Activity Log (/activity)
- **Tab bar**: Overview | ADD | SEARCH
- **Timeline chart** at top (bar chart showing request volume)
- **Table**: Time | Type (ADD/SEARCH badge) | Agent | Event details | Latency | Status (green check)
- Type badges: ADD (green), SEARCH (purple)

#### 5. Pools (/pools) — UNIQUE TO US
- Keep but restyle to match Mem0 aesthetic
- Table: Pool name | Members | Memory Count | Last Updated | Action

#### 6. Settings (/settings)
- API key display (masked)
- Configuration options

### Design Tokens (Dark Theme, Mem0-inspired)
- Background: #0a0a0a (near black)
- Sidebar bg: #111111
- Card bg: #1a1a1a 
- Border: #262626
- Text primary: #fafafa
- Text secondary: #a1a1aa
- Accent green: #22c55e (for ADD badges, success)
- Accent purple: #a855f7 (for SEARCH badges)
- Accent blue: #3b82f6 (for charts)
- Font: Inter/Geist (already using)

### What to SKIP (Mem0 features we don't have)
- Graph Memory page
- Webhooks page
- Memory Exports page
- Playground
- API Keys management page
- Usage & Billing
- Install guide
- Org/project switcher

### API Changes Needed
- Add `/v1/activity/` endpoint to log and return API request history (type, latency, status)
- Add request logging middleware to track ADD/SEARCH/LIST events with timestamps
- Add `/v1/stats/` endpoint for dashboard summary (total memories, request counts, etc.)
