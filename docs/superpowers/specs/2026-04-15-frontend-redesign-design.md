# AURA Frontend Redesign — Design Spec
> Data: 2026-04-15  
> Versione: 1.0  
> Stato: Approvato

---

## 1. Obiettivo

Riscrivere completamente il frontend di AURA da zero con un'interfaccia moderna, ben strutturata e personalizzabile. L'interfaccia deve essere ispirata a Claude.ai / Perplexity, con navigazione a icon rail, area admin separata e strutturata, supporto dark/light mode, theming per tenant e layout mobile nativo.

**Approccio**: rewrite progressivo — prima la shell (layout, routing, design system), poi i componenti nell'ordine giusto. Nessun big bang.

---

## 2. Design System & Visual Language

### Palette colori

```css
/* Light mode */
--bg-base: #fafbff;
--bg-subtle: #f4f6fd;
--bg-muted: #eef1fa;

--surface-1: #ffffff;
--surface-2: #f4f6fd;
--surface-3: #eef1fa;
--surface-hover: #f0f3fc;

--text-primary: #0f0f23;
--text-secondary: #4b5563;
--text-tertiary: #9ca3af;
--text-disabled: #d1d5db;

--accent: #6366f1;           /* indigo */
--accent-secondary: #06b6d4; /* cyan */
--accent-light: #818cf8;
--accent-dark: #4f46e5;
--accent-subtle: rgba(99,102,241,0.08);
--accent-subtle-hover: rgba(99,102,241,0.14);

--gradient-brand: linear-gradient(135deg, #6366f1, #06b6d4);
--gradient-brand-soft: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(6,182,212,0.08));

--success: #10b981;
--warning: #f59e0b;
--danger: #ef4444;
--info: #3b82f6;

--border: rgba(0,0,0,0.07);
--border-strong: rgba(0,0,0,0.12);

--shadow-sm: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
--shadow-md: 0 4px 12px rgba(0,0,0,0.08);
--shadow-accent: 0 4px 24px rgba(99,102,241,0.12);
--shadow-lg: 0 8px 32px rgba(0,0,0,0.1);

/* Dark mode */
--bg-base: #0d0f1a;
--surface-1: #131520;
--surface-2: #1a1d2e;
--surface-3: #1f2235;
--text-primary: #f1f5f9;
--text-secondary: #94a3b8;
--border: rgba(255,255,255,0.07);
```

### Typography

- **Font sans**: Geist (fallback: Inter, system-ui)
- **Font mono**: Geist Mono (fallback: JetBrains Mono, monospace)
- Scale: 12 / 13 / 14 / 15 / 16 / 18 / 20 / 24 / 32px
- Headings: weight 600, letter-spacing -0.02em, line-height 1.25
- Body: weight 400, line-height 1.6
- Caricamento via `next/font/local` o CDN Vercel Geist

### Shape & Motion

- Border radius: 8 / 10 / 12 / 16 / 20 / 24 / 9999px
- Transizioni hover: 150ms ease
- Transizioni panel/drawer: 250ms cubic-bezier(0.4, 0, 0.2, 1)
- Transizioni modal: 200ms ease + scale(0.97 → 1)

### Icone

**Lucide React** — tree-shakeable, coerente, open source.

### Theming tenant

- CSS variables su `<html>` iniettate al bootstrap da `/api/v1/tenant/branding`
- Variabili sovrascrivibili: `--brand-primary`, `--brand-secondary`, `--brand-logo-url`, `--brand-name`
- Dark/light mode sempre controllabile dall'utente indipendentemente dal tema tenant

---

## 3. Layout Shell & Navigazione

### Struttura desktop

```
┌──────────────────────────────────────────────────────┐
│ [44px rail] │ [240px panel] │ [area principale]       │
└──────────────────────────────────────────────────────┘
```

### Icon Rail (44px, fisso a sinistra, `z-index: 40`)

**Contenuto dall'alto al basso:**
1. Logo AURA (24px, gradient brand) — link a `/chat`
2. Separatore sottile
3. Icona **Chat** (`MessageSquare`)
4. Icona **Progetti** (`FolderOpen`)
5. Icona **Spaces** (`Database`)
6. Icona **Agents** (`Bot`)
7. Separatore
8. Icona **Admin** — visibile solo se `roles` include `admin` o `tenant_admin`
9. Fondo: icona **Avatar utente** (24px, iniziali colorate o foto) → apre user menu inline

**Comportamento:**
- Click su icona attiva → toggling del panel contestuale (apre/chiude)
- Click su icona inattiva → seleziona e apre il panel
- Icona attiva: sfondo `accent-subtle`, dot indicator 4px gradient
- Tooltip al hover (150ms delay): nome sezione
- Rail sempre visibile, non collassabile

### Panel contestuale (240px)

**Animazione**: `translateX(-100%)` → `translateX(0)`, 250ms, con overlay semi-trasparente su mobile.

**Vista Chat:**
- Bottone "New Chat" (gradient brand, full width)
- Input ricerca (icona lente, clear button)
- Lista conversazioni raggruppate: Oggi / Ieri / Ultimi 7 giorni / Mese scorso / Più vecchi
- Ogni item: titolo troncato (1 riga) + timestamp relativo + hover → delete button
- Footer: shortcut `⌘K` per ricerca globale

**Vista Progetti:**
- Bottone "Nuovo Progetto" 
- Lista card compact: nome progetto + badge contatore spaces + badge contatore agents
- Item attivo: bordo sinistro 2px gradient brand

**Vista Spaces:**
- Bottone "Nuovo Space"
- Lista: nome + type badge (doc/web/api) + dot status

**Vista Agents:**
- Nessun bottone creazione (solo admin crea agents)
- Lista: nome + status dot (green=published, gray=draft) + slug

**Vista Admin:**
- Navigation tree ad albero con sezioni collassabili (vedi sezione 4)

### Area principale

- `flex: 1`, `overflow: hidden`
- Nessun header globale
- Ogni vista gestisce il proprio header interno
- Max-width chat: 760px centrata con `mx-auto`

### Routing

```
/                         → redirect /chat
/chat                     → empty state chat
/chat/[threadId]          → thread specifico
/settings                 → impostazioni utente
/settings/profile         → profilo
/settings/appearance      → tema, densità, accent
/settings/api-keys        → chiavi personali
/admin                    → redirect /admin/overview
/admin/overview           → dashboard metriche
/admin/llm/providers      → provider LLM
/admin/llm/credentials    → chiavi API provider
/admin/llm/models         → modelli abilitati
/admin/llm/budgets        → budget e limiti costo
/admin/users              → utenti locali
/admin/tenant/config      → impostazioni tenant
/admin/tenant/branding    → logo, colori, nome app
/admin/tenant/auth        → OIDC configuration
/admin/agents             → agent registry
/admin/api-keys           → workspace API keys
```

### Mobile (< 768px)

- Icon rail → **Bottom tab bar** (4 tab fissi: Chat / Progetti / Cerca / Profilo)
- Panel contestuale → **Bottom sheet** che sale dal basso, swipe down per chiudere, handle visibile
- Area principale → full screen, nessun chrome superfluo
- Admin: accessibile via link diretto o da Profilo tab → "Amministrazione" (solo admin)
- Bottom tab bar: `position: fixed; bottom: 0`, safe area inset per iPhone notch
- Tab attivo: icona con gradient brand + label colorata

---

## 4. Area Admin (`/admin/*`)

### Layout admin

```
┌──────────────────────────────────────────────────────┐
│ [44px rail] │ [220px admin-nav] │ [contenuto CRUD]    │
└──────────────────────────────────────────────────────┘
```

Il panel contestuale quando si è in area admin mostra la **admin navigation** — albero con sezioni collassabili, link attivo evidenziato, breadcrumb nell'area contenuto.

### Sezioni admin navigation

```
Overview
─── LLM
    Providers
    Credentials
    Models
    Budgets
─── Utenti
    Utenti locali
─── Tenant
    Configurazione
    Branding
    Autenticazione (OIDC)
─── Agents
    Registry
─── API Keys
    Workspace Keys
```

### Pattern CRUD (standard per ogni pagina)

Ogni pagina admin segue questa struttura verticale:

```
[PageHeader]
  Titolo + descrizione + [Aggiungi X] button

[CreateForm] (collassabile o in modale)
  Campi con validazione inline
  Submit + feedback toast

[DataTable]
  Colonne ordinabili
  Ricerca/filtro inline
  Paginazione (20 righe default)
  Azioni per riga: Edit | Delete | [contestuali]
  Empty state con CTA
```

### Specifiche per pagina

**Overview `/admin/overview`:**
- 4 stat card: Utenti totali / Modelli attivi / Budget consumato % / Agents pubblicati
- Status indicator per ogni sottosistema (LLM connesso, OIDC attivo, ecc.)
- Tabella "Ultimo utilizzo" (ultimi 10 eventi di rilievo)

**LLM → Providers `/admin/llm/providers`:**
- Colonne: Nome, Tipo (openai/anthropic/azure/custom), Status, Azioni
- Form: nome, tipo (select), base_url (opzionale per custom)

**LLM → Credentials `/admin/llm/credentials`:**
- Colonne: Alias, Provider, Ultimo utilizzo, Status (active/error), Azioni
- Form: alias, provider (select), api_key (input type=password con show/hide), note
- Key mascherata nella tabella (`sk-...••••••••`)

**LLM → Models `/admin/llm/models`:**
- Colonne: Alias, Model ID, Provider, Policy, Abilitato (toggle inline), Azioni
- Form: alias, model_id, provider (select), policy template

**LLM → Budgets `/admin/llm/budgets`:**
- Colonne: Scope, Limite ($), Consumato ($), % con barra progresso colorata (verde/giallo/rosso), Reset, Azioni
- Form: scope (tenant/user/space), limite, periodo (daily/monthly)

**Utenti `/admin/users`:**
- Colonne: Email, Nome, Ruolo (badge), Creato il, Ultimo accesso, Azioni
- Form: email, nome, ruolo (select), password temporanea
- Azioni riga: modifica ruolo inline, reset password, disabilita account

**Tenant → Configurazione `/admin/tenant/config`:**
- Form unico: nome tenant, slug, timezone, lingua default

**Tenant → Branding `/admin/tenant/branding`:**
- Form: logo URL (light), logo URL (dark), nome app, accent color (hex picker)
- Live preview inline del tema applicato

**Tenant → Auth `/admin/tenant/auth`:**
- Form OIDC: issuer URL, client_id, client_secret (mascherato), scopes, redirect URI (read-only)
- Bottone "Testa connessione" → verifica endpoint discovery
- Status badge: configured / not configured / error

**Agents → Registry `/admin/agents`:**
- Colonne: Nome, Slug, Versione, Status (badge), Ultimo aggiornamento, Azioni
- Azioni: publish/unpublish toggle, dettaglio (link a pagina agente)
- Nessun form creazione inline (agents creati via deployment)

**API Keys `/admin/api-keys`:**
- Colonne: Alias, Creata il, Ultimo utilizzo, Scopes, Azioni
- Form: alias, scopes (multi-select)
- Key mostrata UNA sola volta al momento della creazione (modale con copy button)
- Delete: confirm dialog con digitazione nome chiave

### UX pattern admin

- **Toast notifications**: stack bottom-right, max 3, auto-dismiss 4s, persist per errori critici
- **Confirm delete**: dialog con testo "Digita `{nome}` per confermare"
- **Badge status**: published=`success`, draft=`text-tertiary`, error=`danger`
- **Skeleton loading**: per tabelle e form al caricamento
- **Empty state**: illustrazione SVG inline + headline + CTA primario

---

## 5. Chat, Composer & Messaggi

### Chat area

- Colonna centrata, max-width 760px, `mx-auto`
- Padding bottom: 140px (spazio per composer sticky)
- Scroll container con `overflow-y: auto`, smooth scroll
- FAB "scroll to bottom" in basso a destra (appare dopo 200px di scroll verso l'alto): icona `ArrowDown`, gradient brand, animazione fade-in

**Empty state:**
- Logo AURA 48px con gradient
- Saluto: "Ciao, {nome}" (da UserIdentity)
- Sottotitolo: "Come posso aiutarti oggi?"
- Griglia 2×2 di prompt suggeriti: card con icona + titolo + descrizione breve, click → compila composer

### Messaggi

**User message:**
- Bolla destra, max-width 72%
- Background: `accent-subtle`, border: 1px `rgba(99,102,241,0.15)`
- Border radius: 16px 16px 4px 16px
- Padding: 10px 14px

**Assistant message:**
- Nessuna bolla — testo libero su sfondo trasparente
- Avatar AURA 20px (gradient icon) a sinistra, top-aligned
- Markdown completo: headings, bold, italic, code inline, code block (syntax highlight con Shiki), tabelle, liste
- Streaming: cursore `▋` animato blink, testo progressivo

**Agent message:**
- Come assistant ma con badge colorato in cima: icona agent + nome agent
- Colore badge unico per agent (generato da hash del nome)

**Azioni hover (appaiono su hover del messaggio):**
- Copy (icona `Copy`)
- Regenerate (solo sull'ultimo messaggio assistant, icona `RefreshCw`)
- Thumbs up / Thumbs down (feedback)

**Citations:**
- Chip inline `[1]` `[2]` nel testo — cliccabili
- Click → espande accordion sotto il messaggio con card per ogni citation: titolo, fonte URL, snippet, score bar

**Artifacts:**
- Card collassabile sotto il messaggio
- Header: icona tipo + label + bottone expand/collapse + bottone download
- Tipi: markdown (rendered), code (syntax highlight + copy), CSV (tabella scrollabile), JSON (tree collassabile), PDF (link + anteprima), immagine (preview)

**Thread header (sopra i messaggi):**
- Titolo conversazione editabile inline (click → input, blur → salva)
- Chip spaces attivi: `#nome-space` con colore type + remove button
- Overflow menu (`...`): Rinomina, Cancella, Esporta (markdown)

### Composer

Container sticky al fondo, `backdrop-blur: 12px`, background `rgba(surface-1, 0.85)`, bordo superiore sottile, `box-shadow: var(--shadow-accent)`.

**Struttura:**

```
[File chips — visibili se file allegati]
[Textarea autosize 1→8 righe]
[Toolbar superiore: @mention | #space | Attach | ModelSelector]
[Toolbar inferiore: char counter | Send button]
```

**Textarea:**
- Placeholder dinamico: "Chatta con AURA..." / "Chatta nel contesto di {progetto}..."
- Max 32.000 caratteri
- Enter = invia, Shift+Enter = nuova riga
- `@` → dropdown autocomplete agents
- `#` → dropdown autocomplete spaces
- `/` → dropdown slash commands (`/clear`, `/help`, `/agents`)

**Toolbar superiore** (visibile solo quando textarea è focused):
- `@` button → apre autocomplete agents
- `#` button → apre autocomplete spaces
- `Paperclip` → file picker (+ drag & drop sull'intera chat area)
- `ModelSelector` → dropdown compatto con lista modelli disponibili

**Toolbar inferiore:**
- Char counter: visibile solo se > 80% del limite, colore warning > 90%, danger > 98%
- Send button: gradient brand, icona `ArrowUp`, disabled se textarea vuota o in streaming

**File chips:**
- Nome file troncato + icona tipo + progress bar durante upload + remove `×`
- Max 5 file contemporaneamente

---

## 6. Settings Utente (`/settings/*`)

Layout a due colonne: nav verticale 200px + contenuto.

### `/settings/profile`
- Avatar: upload immagine o iniziali autogenerate su sfondo gradient
- Nome display, email (read-only se OIDC), cambio password (solo local auth)

### `/settings/appearance`
- Toggle dark / light / system (segue `prefers-color-scheme`)
- Accent color: 6 preset pill (indigo, cyan, violet, emerald, amber, rose) + hex custom
- Densità UI: Comfortable (default) / Compact (riduce padding e font size del 10%)

### `/settings/api-keys`
- Tabella chiavi personali (alias, creata il, ultimo uso)
- Form creazione + reveal-once modale
- Delete con confirm

### `/settings/notifications`
- Toggle notifiche browser (agent completato, errore)

---

## 7. Onboarding (primo accesso)

Triggered se `UserIdentity.onboarding_completed !== true`.

**Step 1 — Benvenuto:**
- Schermata full-page con logo tenant (o AURA), nome app, breve pitch
- CTA "Inizia" → step 2

**Step 2 — Scegli un progetto:**
- Se esistono spaces pubblicati: griglia card selezionabili (nome + tipo)
- Se nessuno space: messaggio "Nessun space configurato ancora — un admin li aggiungerà" + skip
- CTA "Continua"

**Step 3 — Prima chat:**
- Redirect a `/chat`, composer pre-focused
- Placeholder "Cosa vuoi fare oggi?"
- Banner dismissibile: "Suggerimento: aggiungi uno space con `#` per cercare nei documenti"

**Progress pill:**
- Bottom-right, `position: fixed`
- "Setup X/3" — scompare quando `onboarding_completed = true`

---

## 8. Stati globali & Error handling

**Toast system:**
- Stack bottom-right (desktop) / bottom-center (mobile)
- Max 3 visibili contemporaneamente
- Auto-dismiss: 4s success/info, 6s warning, persistent error
- Tipi: success (verde) / error (rosso) / warning (giallo) / info (blu)

**Offline banner:**
- Strip ambra in cima, `position: fixed, top: 0, z-index: 100`
- "Connessione assente — alcune funzionalità non sono disponibili"
- Scompare automaticamente al ripristino

**Error boundary:**
- Pagina friendly: icona, "Qualcosa è andato storto", stack trace in accordion (solo dev), CTA "Ricarica" + "Torna alla chat"

**Loading states:**
- Skeleton per tabelle admin, lista conversazioni, messaggi
- Spinner gradient brand per operazioni puntuali
- Shimmer su card e avatar

---

## 9. Componenti da creare (inventario)

### Shell & Layout
- `AppShell` — layout principale con rail + panel + main
- `IconRail` — barra icone fissa sinistra
- `ContextPanel` — panel contestuale 240px
- `AdminNav` — navigazione albero per area admin
- `BottomTabBar` — navigazione mobile

### Design System
- `Button` — varianti: primary/secondary/ghost/danger, size: sm/md/lg
- `Input` — text, password (show/hide), search
- `Select` — dropdown nativo + custom
- `Badge` — status, type, count
- `Toast` / `ToastStack`
- `Modal` — con overlay, focus trap, ESC close
- `ConfirmDialog`
- `Skeleton`
- `EmptyState`
- `Tooltip`
- `Avatar`

### Admin
- `PageHeader` — titolo + descrizione + CTA
- `DataTable` — colonne, sort, pagina, ricerca, azioni riga
- `StatCard` — metrica con icona e trend
- `StatusBadge`
- `ColorPicker` (hex input + preset swatches)

### Chat
- `ChatArea`
- `MessageBubble` — user / assistant / agent
- `Composer`
- `CitationChip` / `CitationCard`
- `ArtifactCard`
- `PromptSuggestions` — griglia empty state
- `AgentBadge`
- `StreamingCursor`

### Utility
- `ThemeProvider` — dark/light/system + tenant overrides
- `ToastProvider`

---

## 10. Stack tecnico (invariato)

- Next.js 14 App Router
- TypeScript
- Tailwind CSS (configurazione CSS variables rinnovata)
- Zustand (state globale)
- Lucide React (icone)
- Geist font (Vercel)
- Shiki (syntax highlighting)
- Esistenti: `httpx`-based api client, SSE streaming, Zustand store

---

## 11. Approccio implementativo

**Rewrite progressivo in questo ordine:**

1. **Design system**: aggiornare `globals.css` e `tailwind.config.ts` con i nuovi token
2. **Shell**: `AppShell` + `IconRail` + `ContextPanel` + routing aggiornato
3. **Chat**: `ChatArea` + `MessageBubble` + `Composer` (componenti più critici)
4. **Admin**: shell admin + `DataTable` + tutte le pagine CRUD
5. **Settings**: pagine settings utente
6. **Onboarding**: flow primo accesso
7. **Mobile**: `BottomTabBar` + bottom sheet + responsive tuning
8. **Theming**: `ThemeProvider` con tenant overrides + settings aspetto

Ogni step è indipendente e verificabile. Non si inizia lo step N+1 prima che lo step N funzioni.

---

## 12. Non in scope (questa iterazione)

- PWA / service worker
- Internazionalizzazione completa (solo IT/EN placeholder)
- Storybook / component library standalone
- Test E2E (da aggiungere dopo stabilizzazione)
