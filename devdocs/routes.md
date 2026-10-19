# routes.md — All Routes (DSCoaching)

## Public Routes (no auth)

| Method | Path | Function | Purpose |
|--------|------|----------|---------|
| GET | `/` | `index()` | Redirects to dashboard or login |
| GET,POST | `/login` | `login()` | Login form + authentication |
| GET | `/logout` | `logout()` | Clear session, redirect to login |
| GET,POST | `/setup` | `setup()` | First-time admin creation (disabled after first coach) |
| GET,POST | `/register` | `register()` | Coach self-registration |
| GET | `/features` | `features_page()` | Marketing page showing feature list |
| GET | `/lang/<lang>` | `set_language()` | Switch UI language (en/fr), session-based |
| GET | `/font/<font>` | `set_font()` | Switch UI font theme (clean/classic/sharp/modern), session + DB |

## Coach Routes (`@login_required("coach")`)

| Method | Path | Function | Purpose |
|--------|------|----------|---------|
| GET | `/coach` | `coach_dashboard()` | Dashboard with coachee cards, stats |
| GET,POST | `/coach/settings` | `coach_settings()` | Password, name, feature flag toggles |
| GET,POST | `/coach/branding` | `coach_branding()` | Colors, logo, Telegram bot token |
| POST | `/coach/change-password` | `coach_change_password()` | Standalone password change |
| POST | `/coach/change-name` | `coach_change_name()` | Standalone name change |
| GET | `/coach/logo` | `coach_logo()` | Serve logo image (also used by coachees) |
| GET,POST | `/coach/coachee/add` | `add_coachee()` | Create new coachee |
| GET | `/coach/coachee/<cid>` | `coach_view_coachee()` | Full coachee detail view |
| POST | `/coach/coachee/<cid>/edit` | `edit_coachee()` | Update coachee settings, contract, features |
| POST | `/coach/coachee/<cid>/context` | `save_coachee_context()` | Save coach's private notes |
| GET | `/coach/coachee/<cid>/profile-prompt` | `get_profile_prompt()` | Get LLM prompt for AI profile |
| POST | `/coach/coachee/<cid>/profile` | `save_profile()` | Save AI-generated profile (JSON body) |
| POST | `/coach/coachee/<cid>/reset-password` | `reset_coachee_password()` | Reset coachee password |
| GET | `/coach/coachee/<cid>/heatmap` | `compliance_heatmap()` | 90-day compliance visualization |
| GET | `/coach/coachee/<cid>/categories` | `category_breakdown()` | Task stats by category |
| GET | `/coach/coachee/<cid>/summary` | `weekly_summary()` | Weekly summary stats |
| GET | `/coach/coachee/<cid>/contracts` | `contract_history()` | Contract version history |
| GET,POST | `/coach/tasks` | `manage_tasks()` | Create templates, assign tasks |
| GET,POST | `/coach/grading` | `bulk_grading()` | Grade multiple completed tasks |
| GET | `/coach/library-search` | `library_search()` | JSON: search task template library |
| POST | `/coach/template/<tid>/edit` | `edit_template()` | Edit task template |
| POST | `/coach/template/<tid>/delete` | `delete_template()` | Delete task template |
| GET,POST | `/coach/conditioning` | `manage_conditioning()` | Create daily mental prompts |
| POST | `/coach/ack/<cid>` | `give_acknowledgement()` | Positive/negative acknowledgement |
| POST | `/coach/task/<tid>/review` | `review_task()` | Grade a specific task (A-F) |
| POST | `/coach/note/<cid>` | `coach_add_note()` | Send note (optional scheduled) |
| POST | `/coach/note/<nid>/pin` | `pin_note()` | Pin/unpin a note |
| POST | `/coach/quick-note/<cid>` | `quick_note()` | Quick note from dashboard |
| POST | `/coach/quick-ack/<cid>` | `quick_ack()` | Quick acknowledgement from dashboard |
| POST | `/coach/goal/<gid>` | `review_goal()` | Approve/reject coachee goal |
| POST | `/coach/voice/<cid>` | `coach_voice_note()` | Upload voice note |
| GET | `/coach/audit` | `audit_log()` | View audit log |
| GET | `/coach/analyze` | `analyze_text()` | LLM text analysis tool |
| GET,POST | `/coach/support` | `coach_support()` | Support tickets to admin |
| GET | `/coach/help` | `coach_help()` | In-app navigation guide |
| GET,POST | `/coach/photo-validation-settings` | `photo_validation_settings()` | AI photo validation config (service, API key) |
| POST | `/coach/coachee/<cid>/photo-validation` | `update_coachee_photo_validation()` | Set per-coachee validation percentage |
| POST | `/coach/task/<tid>/validate-photo` | `coach_override_photo_validation()` | Coach overrides AI photo decision |
| POST | `/coach/coachee/<cid>/generate-profile` | `generate_profile()` | Trigger server-side AI profile generation |
| POST | `/coach/coachee/<cid>/ai-digest` | `ai_weekly_digest()` | Generate AI activity digest for a coachee |
| GET | `/coach/coachee/<cid>/task-context/<tid>` | `task_context()` | View full context for a task submission |
| POST | `/coach/badge/<cid>` | `award_badge()` | Award a gamification badge to a coachee |
| POST | `/coach/nudge/<cid>` | `nudge_coachee()` | Send a nudge/reminder to a coachee |
| POST | `/coach/conditioning/generate/<cid>` | `generate_conditioning()` | AI-generate a conditioning prompt |
| GET,POST | `/coach/rituals` | `manage_rituals()` | Create/manage recurring rituals |
| GET,POST | `/coach/automations` | `manage_automations()` | Create/manage auto-rules (trigger→action) |
| GET,POST | `/coach/week-plan` | `manage_week_plan()` | Configure weekly recurring task schedule |
| GET,POST | `/coach/onboarding` | `manage_onboarding()` | Configure scripted onboarding sequence |
| GET,POST | `/coach/coachee/<cid>/payments` | `coachee_payments()` | View/configure payment plan + log payments |
| POST | `/coach/coachee/<cid>/quick-pay` | `quick_confirm_payment()` | Log a payment quickly |
| GET | `/coach/coachee/<cid>/writing` | `coach_view_writing()` | View a coachee's creative works archive |
| POST | `/coach/coachee/<cid>/writing/collection` | `create_collection()` | Create a creative collection |
| POST | `/coach/coachee/<cid>/writing/constraint` | `assign_constraint()` | Assign a creative constraint/prompt |
| POST | `/coach/coachee/<cid>/writing/<wid>/note` | `annotate_work()` | Add coach feedback to a creative work |
| GET | `/coach/coachee/<cid>/writing/export` | `export_collection()` | Export a coachee's creative works |

## Coachee Routes (`@login_required("coachee")`)

| Method | Path | Function | Purpose |
|--------|------|----------|---------|
| GET | `/me` | `coachee_dashboard()` | Full dashboard (triggers auto-behaviors) |
| POST | `/me/checkin` | `submit_checkin()` | Submit morning/evening/weekly check-in |
| POST | `/me/task/<tid>` | `complete_task()` | Complete/partial-complete a task |
| POST | `/me/conditioning/<mid>` | `respond_conditioning()` | Respond to mental conditioning prompt |
| POST | `/me/tracking` | `submit_tracking()` | Log food/hydration/alcohol/exercise/emotional |
| POST | `/me/note` | `coachee_add_note()` | Send note to coach |
| POST | `/me/pause` | `trigger_pause()` | Pause or stop coaching (safe word) |
| GET | `/me/history` | `coachee_history()` | View past checkins, logs, notes |
| GET | `/me/export` | `data_export()` | Export all personal data as JSON |
| POST | `/me/goal` | `propose_goal()` | Propose a goal to coach |
| POST | `/me/journal` | `add_journal()` | Add journal entry (optionally shared) |
| POST | `/me/progress-photo` | `add_progress_photo()` | Upload progress photo |
| POST | `/me/voice` | `coachee_voice_note()` | Upload voice note |
| GET | `/me/help` | `coachee_help()` | In-app navigation guide for coachees |
| POST | `/me/ritual/<rid>/complete` | `complete_ritual()` | Mark a ritual complete for today |
| GET | `/me/writing` | `writing_collection()` | View own creative works + active constraints |
| POST | `/me/writing/submit` | `submit_work()` | Submit a new creative work |
| GET | `/me/writing/<wid>` | `view_work()` | View a single creative work |

## File Serving (session required, ownership checked)

| Method | Path | Function | Purpose |
|--------|------|----------|---------|
| GET | `/task/<tid>/attachment` | `task_attachment()` | Serve task photo attachment |
| GET | `/voice/<vid>` | `serve_voice()` | Serve voice note audio |
| GET | `/progress-photo/<pid>` | `serve_progress_photo()` | Serve progress photo |

## Admin Routes (`@admin_required`)

| Method | Path | Function | Purpose |
|--------|------|----------|---------|
| GET | `/admin` | `admin_dashboard()` | All coaches with 7-day activity stats |
| GET,POST | `/admin/coach/add` | `admin_add_coach()` | Create new coach |
| POST | `/admin/coach/<coid>/freeze` | `admin_freeze_coach()` | Toggle freeze (blocks login) |
| POST | `/admin/coach/<coid>/delete` | `admin_delete_coach()` | CASCADE delete coach + all data |
| POST | `/admin/coach/<coid>/reset-password` | `admin_reset_coach_password()` | Reset coach password |
| GET | `/admin/support` | `admin_support()` | View support tickets |
| POST | `/admin/support/<mid>/reply` | `admin_reply_support()` | Reply to support ticket |

## Security Model

- All destructive actions (create, update, delete) are **POST-only**
- Session cookie: `SameSite=Lax`, `HttpOnly=True` — blocks cross-origin POSTs
- Coach can only see/modify their own coachees (WHERE coach_id=%s)
- File serving checks ownership (coachee can only access own files)
- Admin cannot delete themselves or other admins
