# ui-patterns.md — UI Patterns (DSCoaching)

## Design System

Dark theme with CSS custom properties:
```css
:root {
  --accent: #e94560;   /* Per-coach, configurable */
  --bg: #1a1a2e;       /* Per-coach, configurable */
  --card: #16213e;     /* Per-coach, configurable */
  --input: #0f3460;
  --text: #e0e0e0;
  --muted: #888;
  --border: #333;
}
```

Colors are set per-coach (branding) and injected into templates via session:
```html
<style>:root{--accent:{{ session.get('accent','#e94560') }};...}</style>
```

## Layout Patterns

- Nav: sticky top, flex, wraps on mobile
- Coach dashboard: card grid with filter buttons (all, ungraded, no check-in, has strikes)
- Coachee dashboard: tabbed interface (Rules, Morning, Evening, Tasks, Mind, Tracking, Notes, Boundaries, Goals, Journal, Photos)
- All pages: single-column, max-width 900px, responsive

## Template System

- All templates are standalone HTML files in `src/templates/`
- No base template inheritance — each file is complete (keeps template loading simple and explicit)
- Loaded via `_tpl(name)` → `render_template_string(content, **context)`
- Context processor `inject_helpers()` provides `flash_block` to all templates

## Flash Messages

Rendered by the context processor before template render:
```python
@app.context_processor
def inject_helpers():
    messages = get_flashed_messages(with_categories=True)
    html = "".join(f'<div class="flash flash-{cat}">{msg}</div>' ...)
    return {"flash_block": html}
```

Templates include `{{ flash_block }}` after `</nav>`. Categories: `success` (green), `error` (red), `info` (subtle).

## Onboarding

New coachees see a welcome banner for their first 3 logins:
- Tracked via `coachee.login_count` (incremented on login)
- Banner styled with accent border, explains what to expect
- Disappears after 3rd login

Empty states shown when no data exists:
- "No contract set yet. Your coach will define the rules here."
- "No pending tasks right now. Check back after your unveil time."
- "No messages yet. Send a note above to start communicating with your coach."
- "No goals yet. Propose one above and your coach will review it."
- "Start journaling to track your thoughts and progress."
- "Upload progress photos to track your journey visually."

## Error Pages

Styled `error.html` template with dark theme, error code, friendly message, back/home links. Registered for 404, 403, 500.

## Form Patterns

- All forms use `method="post"` with standard form fields
- No AJAX for primary actions — full page reload via redirect-after-POST (PRG pattern)
- Exception: LLM profile generation uses client-side fetch to Mistral API
- File uploads: base64 data URI via JS `FileReader` → hidden input → server decodes
- Telegram notifications: client-side JS fetch to Telegram API (privacy: token stays in browser, never hits our server)

## Coachee Dashboard Tabs

Tabs controlled by vanilla JS: clicking a tab shows the matching panel, hides others. Active state via CSS class.

```javascript
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    });
});
```

## Badges & Indicators

The coachee dashboard uses badge counts on tabs:
- Tasks pending count
- Morning check-in (0 or 1)
- Evening check-in (0 or 1)
- Conditioning prompts pending
- Unread notes

## Emoji Usage

Emojis serve as lightweight icons throughout:
- Page titles: 🏠 🔐 📋 🧠 💬 🎯 📓 📸
- Coachee avatars: configurable emoji (default 🐕)
- Grade indicators: letter grades styled with color
- Streak display: 🔥 for active streaks
