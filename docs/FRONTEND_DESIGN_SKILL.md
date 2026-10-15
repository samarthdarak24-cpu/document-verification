---
name: docutrace-frontend-design
description: >
  Authoritative frontend design and implementation skill for DocuTrace — the
  Intelligent Document Verification & Similarity Detection System. Load this
  whenever working on the DocuTrace UI: visual design, motion design, component
  construction, route structure, animation, the DAA Laboratory, or any change to
  the React + TypeScript + Vite + Tailwind client. It fixes the creative
  direction, the colour system, the typography scale, the component inventory,
  the motion design system, and the milestone order of work.
---

# DOCUTRACE — PREMIUM FRONTEND DESIGN & IMPLEMENTATION SKILL

---

## 1. PREAMBLE

This document is the single source of truth for the DocuTrace frontend. Every
visual decision, every component, every animation, and every millisecond of
motion must be traceable back to a rule stated here. Where this document is
silent, the implementer chooses the option most consistent with the creative
direction — never the option that is merely fastest to build.

DocuTrace is not a generic SaaS dashboard. It is an instrument. It should feel
like something a forensic document examiner would keep open on a second monitor
all day: quiet, precise, unhurried, and utterly trustworthy.

---

## 2. CREATIVE DIRECTION

### 2.1 Concept

**"Document Intelligence Studio."**

The product is a studio — a working room — not a marketing page. The interface
should read as the surface of a professional instrument: matte, low-glare,
high-contrast where it matters, and completely free of decoration that does not
carry information.

### 2.2 Central metaphor

**A document under examination.**

Every screen should be legible as one phase of examining a document:

- It arrives (upload)
- It is read (extraction, text, structure)
- It is measured (similarity, edit distance, hashes)
- It is compared against precedent (duplicate detection, template matching)
- It is ruled upon (verification decision, rule engine)
- It is filed (reports, history, audit trail)

Motion, colour, and layout all reinforce this arc. The user is never "using an
app" — the user is **conducting an examination**.

### 2.3 Design principles

1. **Restraint over ornament.** If an element does not inform, remove it.
2. **Editorial, not dashboard.** Typography and hairlines carry the structure —
   not nested cards, not gradients, not coloured panels.
3. **Evidence first.** Numbers, hashes, scores, and rule IDs are always visible
   and always monospaced. The user must be able to audit any conclusion.
4. **One accent, used sparingly.** Brass is a pointing gesture, never a wash.
5. **Motion explains, never entertains.** Every animation answers "what just
   happened?" or "where did this come from?"
6. **Quiet by default, loud only on failure.** Success is calm. Failure is
   unmistakable.
7. **Density is a feature.** This is a professional tool. Respect the user's
   screen; do not waste it on whitespace theatre.
8. **Never lie with colour.** Status colours are semantic and fixed.

### 2.4 Anti-patterns — explicitly forbidden

- Purple/blue "AI startup" gradients
- Glassmorphism, frosted panels, backdrop blur as decoration
- Soft drop shadows on everything; neumorphism
- Rounded-everything (pill buttons on 4px-radius cards)
- Emoji as UI iconography
- Animated blobs, particle fields, floating orbs
- Dark mode with a saturated accent glow
- Centered hero text over a stock photo of a laptop
- "Loading..." spinners without context

---

## 3. COLOUR SYSTEM

Defined once, as CSS custom properties, and never hardcoded anywhere else.

| Token           | Hex       | Role                                                       |
| --------------- | --------- | ---------------------------------------------------------- |
| `--canvas`      | `#F6F7F5` | Application background. A cool off-white, faintly green.   |
| `--ink`         | `#202824` | Primary text. A near-black with a green undertone.         |
| `--forest`      | `#285548` | Primary brand colour. Headings, primary actions, charts.   |
| `--forest-dark` | `#193C32` | Pressed states, depth, dark chart series, sidebar.         |
| `--sage`        | `#DCE8E0` | Quiet fills: selected rows, inert chips, code blocks.      |
| `--brass`       | `#A77C43` | The single accent. Focus rings, active nav, key emphasis.  |
| `--divider`     | `#E0E5E0` | All hairlines and borders. Nothing darker for structure.   |
| `--error`       | `#B54D48` | Failure, rejection, critical mismatch.                     |
| `--warning`     | `#A66A2B` | Caution, mandrel review required, degraded extraction.     |
| `--success`     | `#327657` | Passed, verified, accepted.                                |

### 3.1 Application rules

- **Background is always `--canvas`.** Never pure white, never grey.
- **Body text is `--ink`.** Secondary text is `--ink` at 65% opacity — never a
  separate grey token.
- **Borders are exclusively `--divider`, 1px.** No 2px borders except focus.
- **`--forest` is the only structural colour.** Sidebar active state, table
  headers, chart axes.
- **`--brass` appears at most twice per viewport.** Focus ring + one emphasis.
  It is a scalpel.
- **Status colours are never used for decoration.** If something is
  `--success`, it passed. Nothing else may be green.
- **Tints are produced with `color-mix()`**, not with new tokens. e.g.
  `color-mix(in oklab, var(--error) 8%, var(--canvas))` for an error row fill.

### 3.2 Status semantics

| Meaning                | Colour     | Also requires                    |
| ---------------------- | ---------- | -------------------------------- |
| Passed / verified      | `--success`| A check glyph and the word       |
| Review required        | `--warning`| A glyph and the reason           |
| Failed / rejected      | `--error`  | A glyph, the reason, the rule ID |
| Informational          | `--forest` | Nothing extra                    |
| Disabled / inert       | `--divider`| 45% opacity text                 |

Never rely on colour alone. Every status carries a glyph and a word.

---

## 4. TYPOGRAPHY

Three families. Each has exactly one job.

| Family          | Role                                                                 | Weights      |
| --------------- | -------------------------------------------------------------------- | ------------ |
| **Manrope**     | UI text: navigation, labels, buttons, table cells, body copy.         | 400/500/600/700 |
| **Newsreader**  | Editorial voice: page titles, section titles, pull quotes, empty states. | 400/500/600 italic |
| **IBM Plex Mono** | All evidence: hashes, scores, rule IDs, timings, JSON, file paths.  | 400/500/600  |

### 4.1 Scale

A modular scale, 1.200 ratio, base 15px for UI density.

| Token         | Size / Line-height | Family      | Use                          |
| ------------- | ------------------ | ----------- | ---------------------------- |
| `display`     | 44 / 52            | Newsreader  | Landing hero only            |
| `title-1`     | 30 / 38            | Newsreader  | Page titles                  |
| `title-2`     | 22 / 30            | Newsreader  | Section titles               |
| `title-3`     | 17 / 24            | Manrope 600 | Card titles                  |
| `body`        | 15 / 24            | Manrope 400 | Default                      |
| `body-strong` | 15 / 24            | Manrope 600 | Emphasis                     |
| `small`       | 13 / 20            | Manrope 400 | Secondary text               |
| `label`       | 11 / 16            | Manrope 600 | Uppercase labels, 0.08em     |
| `mono`        | 13 / 20            | IBM Plex Mono | Evidence                   |
| `mono-sm`     | 11.5 / 18          | IBM Plex Mono | Dense tables, hashes       |

### 4.2 Typographic rules

- **Numerals in tables are always tabular**: `font-variant-numeric: tabular-nums`.
- **Labels are uppercase, letter-spaced 0.08em, 11px, `--ink` at 60%.** They sit
  above the value, never beside it.
- **Newsreader is never used below 17px.** It is a display face.
- **Never centre body text.** Only heroes and empty states may centre.
- **Maximum measure for prose is 68ch.** Any longer and it must break into
  columns or a callout.
- **Hashes and IDs are never wrapped, never truncated silently.** If they must
  truncate, truncate in the middle with an ellipsis and show the full value in a
  tooltip and a copy affordance.

---

## 5. TECH STACK

| Concern                | Choice                                                    |
| ---------------------- | --------------------------------------------------------- |
| Framework              | React 19                                                  |
| Language               | TypeScript (strict)                                       |
| Build                  | Vite                                                      |
| Styling                | Tailwind CSS, configured against the tokens in §3 / §4    |
| Motion                 | GSAP + ScrollTrigger + Flip                               |
| Smooth scroll          | Lenis (landing page only — never inside the app shell)    |
| Routing                | React Router                                              |
| Server state           | TanStack Query                                            |
| Forms                  | React Hook Form + Zod                                     |
| Icons                  | Lucide React                                              |
| Primitives             | shadcn/ui on Radix UI                                     |
| Graph visualisation    | React Flow (BFS/DFS trees, dependency graphs, max-flow)   |
| Charts                 | Recharts (benchmarks, analytics)                          |
| Client state           | Zustand (UI preferences, laboratory session state)        |
| Dropzone               | react-dropzone                                            |
| PDF viewing            | react-pdf                                                 |
| Code/text viewing      | Monaco (JSON reports, structured extraction output)       |

### 5.1 Library responsibility map

| Library                   | Responsibility in DocuTrace                                                        |
| ------------------------- | ---------------------------------------------------------------------------------- |
| **React + TypeScript**    | Frontend architecture, typed contracts mirroring the FastAPI schemas                |
| **GSAP**                  | Hero animations, document transitions, algorithm playback step transitions          |
| **Lenis**                 | Smooth scrolling on the landing page only                                           |
| **Tailwind CSS**          | Styling and design tokens                                                           |
| **shadcn/ui**             | Accessible primitives (dialog, select, tabs, tooltip, popover, toast, sheet)        |
| **React Flow**            | BFS/DFS traversal trees, pipeline dependency graph, bipartite matching, max-flow    |
| **Recharts**              | Benchmark and analytics charts                                                      |
| **TanStack Query**        | Backend data fetching, caching, invalidation, optimistic updates                    |
| **Zustand**               | Cross-page client state that is not server state                                    |

### 5.2 Build order directive

> **Build the normal document verification workflow first, then the animated DAA
> Laboratory.**

The verification workflow is the product. The Laboratory is the proof. A user
must be able to complete a full examination — upload, extract, verify, compare,
rule, report — before a single algorithm animation exists.

---

## 6. LAYOUT SYSTEM

### 6.1 App shell

- **Sidebar:** 236px fixed, `--forest-dark` background, vertical rule on the
  right. Groups: Overview / Analysis / DAA Laboratory / Analysis & Config.
  Active item is `--brass` text with a 2px `--brass` left rule.
- **Content column:** `--canvas`, max-width 1280px, gutters 32px.
- **Page header:** Newsreader `title-1`, an optional one-line deck in `small`,
  and a right-aligned action cluster. Separated from content by a `--divider`
  hairline.
- **Vertical rhythm:** all spacing is a multiple of 4px. Section gaps are 40px.
  Card internal padding is 20px.

### 6.2 Grid

- 12-column fluid grid, 24px gutters.
- Dense evidence views (tables over 8 rows) span full width and ignore the grid.
- Laboratory and analysis views favour a 4/8 split: controls left, output right.
- Never nest more than two levels of card.

### 6.3 Surfaces

- Cards are `--canvas` with a 1px `--divider` border and a 2px radius. **No
  shadow.** Depth is communicated by border and spacing, not by blur.
- `shadow-card` exists but is reserved for elements that physically float:
  popovers, dropdowns, dialogs, drag previews.
- `shadow-raised` is reserved for modals and the command palette.

---

## 7. COMPONENT INVENTORY (24)

Every one of these must exist, be typed, be accessible, and be documented in the
style guide route.

| # | Component                | Notes                                                                 |
| - | ------------------------ | --------------------------------------------------------------------- |
| 1 | `AppShell`               | Sidebar + content + health footer + skip link                          |
| 2 | `NavGroup` / `NavItem`   | Collapsible groups; `--brass` active state                             |
| 3 | `PageHeader`             | Title, deck, breadcrumb, action cluster                                |
| 4 | `Hairline` / `Divider`   | The only structural separator                                          |
| 5 | `Card`                   | Border, 2px radius, no shadow; `CardHeader` / `CardBody` / `CardFooter`|
| 6 | `Label`                  | Uppercase 11px, letter-spaced 0.08em                                   |
| 7 | `Stat`                   | Value (mono, tabular) + label + optional delta glyph                   |
| 8 | `DataTable`              | Sticky header, tabular numerals, row selection, sort, keyboard nav      |
| 9 | `Chip` / `StatusChip`    | Semantic, with glyph; never colour-only                                |
| 10 | `Button`                 | `primary` (forest), `brass`, `ghost`, `danger`; loading + disabled      |
| 11 | `Input` / `Textarea`     | 1px divider border, brass focus ring                                   |
| 12 | `Select` / `Combobox`    | Radix-based, keyboard complete                                         |
| 13 | `Dialog` / `Sheet`       | `shadow-raised`, focus trap, Esc to close                              |
| 14 | `Tooltip`                | For truncated hashes, rule IDs, icon-only buttons                      |
| 15 | `Toast`                  | Bottom-right, auto-dismiss, one per action                             |
| 16 | `Dropzone`               | react-dropzone; drag state uses `--sage`, rejection uses `--error`      |
| 17 | `FileCard`               | Name, size, hash, type glyph, extraction status                        |
| 18 | `DocumentViewer`         | react-pdf; page nav, zoom, text-layer highlight of matched spans       |
| 19 | `DiffViewer`             | Side-by-side word-level LCS diff with insert/delete/equal run colouring |
| 20 | `ScoreMeter`             | 0–1 similarity; forest fill, brass tick at the decision threshold      |
| 21 | `RuleRow`                | Rule ID (mono), verdict chip, evidence, expandable rationale           |
| 22 | `AlgorithmTracePlayer`   | Step playback: prev / next / play / pause / reset / speed              |
| 23 | `GraphCanvas`            | React Flow; typed nodes, layout per algorithm, GSAP edge reveal        |
| 24 | `EmptyState`             | Newsreader heading, one sentence, one action                           |
| 25 | `ErrorState`             | `--error` rule, the reason, the retry action                           |
| 26 | `Skeleton`               | Matches the final layout exactly; no shimmer gradients                 |
| 27 | `CommandPalette`         | ⌘K; navigate, run algorithm, jump to document                          |
| 28 | `StyleGuide`             | Internal route rendering every token and component                     |

> The inventory is nominally 24; entries 25–28 are mandatory extensions found
> necessary during implementation. Treat all 28 as required.

---

## 8. MOTION DESIGN SYSTEM

### 8.1 Principles

1. **Purpose.** Every animation must be justified by §2.2 — it shows the
   examination progressing.
2. **Ease.** Entrances use `power2.out`; exits use `power2.in`; continuous
   playback uses `none`. Never `bounce`, never `elastic`.
3. **Duration.** Micro 120ms · standard 240ms · structural 420ms · ceremonial
   720ms (hero only). Nothing exceeds 720ms except a scrubbed timeline.
4. **Stagger.** 40ms between siblings in a list; 60ms between grid cells.
5. **Distance.** Entrances travel at most 12px. Large travel is a page
   transition, not a component entrance.
6. **Interruptibility.** Every animation must be safely killable mid-flight.
   Use `gsap.context()` and revert on unmount.
7. **Reduced motion.** `prefers-reduced-motion: reduce` collapses every
   animation to an instant state change — not a shortened one. The
   `AlgorithmTracePlayer` still works; it just stops tweening.

### 8.2 Named behaviours

| Behaviour              | Trigger                          | Motion                                                                 |
| ---------------------- | -------------------------------- | ---------------------------------------------------------------------- |
| Hero settle            | Landing mount                    | Newsreader title rises 12px, 720ms, stagger 60ms per line               |
| Hairline draw          | Section enters viewport          | `scaleX` 0→1 from left, 420ms, `power2.out`                             |
| Document arrival       | File dropped                     | FileCard scales 0.98→1 and fades, then hash chips stagger in 40ms       |
| Extraction reveal      | Extraction completes             | Page thumbnails stagger 60ms; extracted fields tick in mono             |
| Score settle           | Similarity computed              | `ScoreMeter` fill 0→value, 420ms, `power2.out`; threshold tick at 240ms |
| Match highlight        | Duplicate confirmed              | Matched spans wash to `--sage` with a 2px `--brass` underline, 240ms    |
| Diff line reveal       | Diff view mounts                 | Lines stagger 10ms; insert/delete backgrounds fade in 240ms             |
| Rule cascade           | Verification completes           | `RuleRow`s cascade 40ms each; failures rise 2px and settle              |
| Node traversal         | Playback step (BFS/DFS/flow)     | Visited node fills `--sage`; edge draws `strokeDashoffset`, 240ms       |
| Flip to detail         | Grid → detail navigation         | GSAP `Flip` from FileCard to detail header, 420ms                       |
| Report seal            | Report generated                 | A single `--brass` rule draws across the report card, 420ms             |
| Error emphasis         | Request fails                    | Card border flashes `--error` twice, 120ms each, then holds 1px         |
| Sidebar active         | Route change                     | `--brass` left rule height tweens 120ms                                 |
| Command palette        | ⌘K                               | Backdrop 120ms; panel 240ms `power2.out`, origin top-centre             |

### 8.3 Scroll

**Lenis is permitted on the landing page only.** Inside the app shell the native
scroll is kept, because nested smooth-scroll breaks `DataTable` and
`DocumentViewer`.

`ScrollTrigger` drives: hairline draws, section reveals, the landing page's
examination narrative, and the pinned algorithm-explainer sequence. It must
never drive anything inside a scrollable sub-panel.

---

## 9. ROUTE STRUCTURE

| Path                | Page                                                              |
| ------------------- | ----------------------------------------------------------------- |
| `/`                 | Landing — the examination narrative (Lenis + ScrollTrigger)       |
| `/dashboard`        | Overview: counts, recent activity, system health                  |
| `/documents`        | Evidence list: sortable, filterable, selectable                   |
| `/documents/:id`    | Examination view: viewer, text, structure, fields, runs, rules    |
| `/upload`           | Intake: dropzone, queue, progress, per-file outcome               |
| `/compare`          | Two-document comparison: scores, diff, field changes              |
| `/duplicates`       | Duplicate groups, cluster view, merge/reject decisions            |
| `/templates`        | Template editor: fields, patterns, sections, aliases              |
| `/reports`          | Generated reports: list, viewer, PDF/JSON download                |
| `/lab`              | DAA Laboratory hub                                                |
| `/lab/unit-1` … `/lab/unit-6` | Per-unit algorithm workbench with trace playback          |
| `/performance`      | Benchmarks: charts, tables, complexity validation                 |
| `/settings`         | Runtime configuration                                             |
| `/style-guide`      | Every token and component, internal only                          |
| `*`                 | 404                                                               |

---

## 10. THE DAA LABORATORY

The Laboratory is DocuTrace's distinguishing surface. It must not be a form with
a JSON box.

### 10.1 Per-unit structure

Each of Units I–VI gets: a short editorial preamble tying it to a real
verification problem, a list of its algorithms, and a workbench. The workbench
has:

1. **Input panel** — typed inputs, never raw JSON only. Prefilled with a
   realistic document-verification payload, with a "load sample" control.
2. **Run panel** — run, timing (mono, ms with 3 decimals), operation count.
3. **Trace panel** — the `AlgorithmTracePlayer` over the algorithm's step
   records, with a scrubber, step counter, and a plain-language caption for the
   current step.
4. **Visualisation panel** — `GraphCanvas` where the algorithm has structure
   (traversal, topological sort, inflow/outflow, matching, Huffman tree).
5. **Result panel** — mono output, copyable.
6. **Theory strip** — recurrence, complexity (best/average/worst), in-place and
   stable flags, and the correctness argument in 3–5 sentences.

### 10.2 Trace playback contract

The backend must return a deterministic, finite step list per run:

```ts
type TraceStep = {
  index: number;
  caption: string;        // human sentence for this step
  state: Record<string, unknown>; // algorithm-specific snapshot
};
```

Player controls: `⟨ prev` · `play`/`pause` · `next ⟩` · `reset` · speed
(0.5× / 1× / 2× / 4×). Keyboard: `←`/`→` step, `Space` toggle, `R` reset.
Playing advances on a GSAP timeline so speed and pause are exact.

---

## 11. DATA AND STATE

- **Server state:** TanStack Query exclusively. Query keys are tuples starting
  with the resource name. Mutations invalidate by prefix.
- **Client state:** Zustand, one store per concern (`ui`, `lab`, `filters`).
  Never mirror server state into Zustand.
- **Forms:** React Hook Form with a Zod resolver. The Zod schema mirrors the
  Pydantic schema on the server; disagreement between them is a bug.
- **Errors:** every fetch surfaces a typed error with the server's `detail` and
  `code`. A failed request renders `ErrorState` with the reason and a retry —
  never a bare toast.
- **Optimistic updates** only where the server is idempotent and fast (settings,
  template edits). Never optimistically update a verification decision.

---

## 12. ACCESSIBILITY

- Every interactive element is reachable and operable by keyboard.
- Focus is always visible: 2px `--brass` ring, 2px offset. Never
  `outline: none`.
- `DataTable` implements arrow-key navigation, Home/End, and Space to select.
- `GraphCanvas` nodes are focusable and expose `aria-label` with the node's
  algorithm state.
- The `AlgorithmTracePlayer` announces step changes through a polite live
  region.
- Colour is never the sole carrier of meaning (§3.2).
- Minimum contrast: 4.5:1 for body, 3:1 for large text and UI boundaries.
- All icons that stand alone carry `aria-label`.

---

## 13. PERFORMANCE

- Route-level code splitting; the Laboratory and Monaco load lazily.
- `react-pdf` worker configured and cached; only visible pages render.
- Virtualise `DataTable` beyond 100 rows.
- GSAP timelines are created in `useLayoutEffect` inside `gsap.context()` and
  reverted on unmount.
- Trace playback stores steps in a ref, not React state, and mutates DOM
  directly via GSAP — re-rendering per step is forbidden.
- Keep the main bundle under 900 kB gzipped; report the number in CI output.

---

## 14. MILESTONE ORDER

Implement strictly in this order. Do not begin a milestone before the previous
one renders and works.

1. **Audit.** Read the existing frontend, catalogue what exists, list what is
   missing against §7, and write `docs/FRONTEND_AUDIT.md`.
2. **Plan.** Produce the visual design plan: token table, type scale, shell
   wireframe, and the component-to-route map. Confirm it before building.
3. **Foundation.** Vite + TS strict + Tailwind configured against §3/§4;
   `AppShell`, routing, health indicator, `ErrorState`, `Skeleton`.
4. **Primitives.** `Card`, `Label`, `Stat`, `Chip`, `Button`, `Input`,
   `Select`, `Dialog`, `Tooltip`, `Toast` — plus `/style-guide`.
5. **Verification workflow.** `Documents`, `Upload`, `DocumentDetail`,
   `Compare`, `Templates`, `Reports`. This is the product; it must be complete
   and correct before anything animated exists.
6. **Duplicate intelligence.** `Duplicates` with cluster view, `GraphCanvas`
   for duplicate relationships, merge/reject flows.
7. **Dashboard.** Overview stats, recent activity, health, empty states.
8. **Performance.** `Performance` with Recharts, complexity overlay, raw table.
9. **Laboratory hub.** `/lab` index.
10. **Laboratory units.** `/lab/unit-1` … `/lab/unit-6` with typed inputs,
    `AlgorithmTracePlayer`, `GraphCanvas`, and the theory strip.
11. **Landing page.** Lenis + ScrollTrigger examination narrative. Built last,
    because it must promise exactly what the app delivers.
12. **Motion pass.** Apply §8 across every surface; audit reduced-motion.
13. **Hardening.** Accessibility sweep, keyboard audit, contrast check, bundle
    budget, Vitest + React Testing Library for components and hooks, Playwright
    for the critical path.

---

## 15. QUALITY BAR

A surface is done only when all of these are true:

- It renders correctly at 1280, 1440, and 1920px, and at 200% zoom.
- It has a loading state, an empty state, and an error state.
- It is fully keyboard operable.
- It passes `prefers-reduced-motion`.
- Every number on it is monospaced and tabular.
- No colour is decorative.
- No component uses a shadow inside the app shell.
- No string is hardcoded in more than one place.
- It has at least one test.

---

## 16. NON-NEGOTIABLES

1. Build the **normal document verification workflow first**, then the animated
   DAA Laboratory.
2. The colour tokens in §3 and the type scale in §4 are final. Extend by
   `color-mix()`, never by inventing tokens.
3. Evidence is always monospaced. No exceptions.
4. Status is never colour-only.
5. Motion is capped at 720ms and must be interruptible.
6. Reduced motion collapses animations to state changes; it does not shorten
   them.
7. Lenis never runs inside the app shell.
8. No animation may block or delay a user action.
9. Every route has loading, empty, and error states.
10. The verification workflow is the product. Treat it with the most care.

---

**Build the normal document verification workflow first, then the animated DAA
Laboratory.**
