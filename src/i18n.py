"""Internationalization (i18n) module for DSCoaching.

Session-based language switching. Default: English.
Supported languages: en, fr.
"""

from flask import session

SUPPORTED_LANGS = ("en", "fr")
DEFAULT_LANG = "en"


def get_lang():
    """PURPOSE: Return the current UI language from the session (defaults to en).
    CALLED BY / SCREEN: t() here, and the template helper/context processor in helpers.py — used
    on every rendered screen (coach, coachee, admin, public).
    WHEN: on each translation lookup / template render (per request)."""
    return session.get("lang", DEFAULT_LANG)


def t(key, **kwargs):
    """PURPOSE: Translate a key into the current language, with optional {placeholder} formatting;
    falls back to English then the raw key.
    CALLED BY / SCREEN: exposed to Jinja templates (via helpers inject_helpers) as `t(...)` — used
    across all screens for navigation, help pages, and photo-validation labels.
    WHEN: on template render, whenever a translated string is emitted."""
    lang = get_lang()
    table = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG])
    text = table.get(key, TRANSLATIONS[DEFAULT_LANG].get(key, key))
    if kwargs:
        text = text.format(**kwargs)
    return text


# ── Translation tables ──

TRANSLATIONS = {
    "en": {
        # Navigation
        "nav.tasks": "Tasks",
        "nav.insights": "Insights",
        "nav.settings": "Settings",
        "nav.help": "Help",
        "nav.logout": "Logout",
        "nav.history": "History",
        "nav.export": "Export",
        "nav.manage_tasks": "Manage Tasks",
        "nav.grade_submissions": "Grade Submissions",
        "nav.conditioning": "Conditioning",
        "nav.rituals": "Rituals",
        "nav.automations": "Automations",
        "nav.week_plan": "Week Plan",
        "nav.onboarding": "Onboarding",
        "nav.analyze_text": "Analyze Text",
        "nav.audit_log": "Audit Log",
        "nav.account": "Account",
        "nav.branding": "Branding",
        "nav.support": "Support",
        "nav.admin_panel": "Admin Panel",
        "nav.add_coachee": "+ Add Coachee",
        "nav.language": "Language",

        # Help page - Coach
        "help.title": "Navigation Guide",
        "help.subtitle": "Where to find everything in DSCoaching",
        "help.section.dashboard": "Dashboard",
        "help.dashboard.desc": "Your home screen. Shows all your coachees at a glance with their stats: pending tasks, completion rate, average grade, streak, strikes, check-in status, engagement score, and inactivity alerts.",
        "help.dashboard.actions": "Quick actions from each coachee tile: send a note, give acknowledgement, view details.",
        "help.section.tasks": "Tasks & Assignments",
        "help.tasks.manage": "Manage Tasks — Create task templates (one-time, recurring, reserve). Assign to one or many coachees. Set categories, difficulty, due dates.",
        "help.tasks.grade": "Grade Submissions — Bulk-grade all pending submissions on one page. Give A-F grades with comments.",
        "help.tasks.reserve": "Reserve Tasks — Auto-assigned if you haven't sent anything by the coachee's unveil time. Protects your authority without requiring daily action.",
        "help.tasks.recurring": "Recurring Tasks — Auto-assign every N days with optional variance (±25%) for unpredictability.",
        "help.tasks.library": "Task Library — Save templates with 'in library' flag. Search and reuse across coachees. See usage history.",
        "help.tasks.dependencies": "Task Dependencies — Set a task to unlock only after another is completed.",
        "help.tasks.photo": "Photo Proof — Coachees can attach photos to submissions. You review them in grading.",
        "help.section.communication": "Communication",
        "help.comm.notes": "Notes — Bidirectional messages. Pin important ones. Schedule delivery for a specific time.",
        "help.comm.voice": "Voice Notes — Record and send audio directly from the browser.",
        "help.comm.conditioning": "Mental Conditioning — Daily prompts (shared or per-coachee). Coachees must respond.",
        "help.comm.ack": "Acknowledgements — Quick positive/negative feedback. Shown prominently on the coachee's dashboard.",
        "help.section.tracking": "Tracking & Analytics",
        "help.track.checkins": "Check-ins — Morning/evening structured entries from coachees. Timestamped and immutable.",
        "help.track.logs": "Tracking Logs — Food, hydration, alcohol, exercise, emotional regulation entries.",
        "help.track.heatmap": "Compliance Heatmap — 90-day calendar view (green/yellow/red per day).",
        "help.track.categories": "Category Breakdown — Performance stats per task type.",
        "help.track.weekly": "Weekly Summary — Auto-generated report card visible to both coach and coachee.",
        "help.section.coachee_mgmt": "Coachee Management",
        "help.mgmt.view": "Coachee View — Full detail page: recent tasks, check-ins, notes, conditioning, profile, journal, photos, goals.",
        "help.mgmt.contract": "Contract — Edit rules and terms (versioned history). Only you can modify.",
        "help.mgmt.context": "Private Notes — Your private notes about the coachee's trajectory. Not visible to them.",
        "help.mgmt.features": "Feature Overrides — Enable/disable features per coachee (tasks, check-ins, tracking, journal, etc.).",
        "help.mgmt.profile": "AI Profile — Generate a psychological profile from all coachee data using AI.",
        "help.mgmt.safeword": "Safe Word — Each coachee has a configurable safe word. 'RED' = full stop. Other words = pause.",
        "help.section.automation": "Automation",
        "help.auto.rules": "Auto-Rules — Trigger actions on events (task completed, missed, streak milestone). Auto-notes, auto-acks.",
        "help.auto.onboarding": "Onboarding — Schedule tasks/notes for new coachees' first 7 days.",
        "help.auto.weekplan": "Week Plan — Pre-assign templates to days of the week.",
        "help.section.settings": "Settings & Personalization",
        "help.settings.account": "Account — Change password, update name.",
        "help.settings.branding": "Branding — Logo, accent color, background, card color. Visible to your coachees.",
        "help.settings.features": "Feature Toggles — Global on/off for each feature module.",
        "help.settings.telegram": "Telegram — Set bot token for push notifications on grades and acks.",
        "help.section.tools": "Tools",
        "help.tools.analyze": "Text Analyzer — Paste any conversation or text for AI psychological analysis.",
        "help.tools.audit": "Audit Log — Every action logged with timestamp, IP, and user agent.",

        # Help page - Coachee
        "help.coachee.title": "Your Guide",
        "help.coachee.subtitle": "How your coaching space works",
        "help.coachee.section.rules": "Rules Tab",
        "help.coachee.rules.desc": "Your contract and current level. Shows your streak, progress bar to next level, and earned badges.",
        "help.coachee.section.checkins": "Morning & Evening Check-ins",
        "help.coachee.checkins.desc": "Structured entries to start and end your day. Include mood rating. Immutable once submitted — no edits possible.",
        "help.coachee.section.tasks": "Tasks",
        "help.coachee.tasks.desc": "Assignments from your coach. Each has a due time (freeze time). Complete with text response and optional photo proof. You can mark as partial if needed.",
        "help.coachee.tasks.streak": "Streak — Consecutive days with all tasks completed on time. Resets on any missed task.",
        "help.coachee.tasks.grades": "Grades — Your coach grades A-F with comments. Visible in the graded tasks section.",
        "help.coachee.section.conditioning": "Mental Conditioning",
        "help.coachee.conditioning.desc": "Daily prompts from your coach. Respond thoughtfully — these build your psychological profile.",
        "help.coachee.section.tracking": "Tracking",
        "help.coachee.tracking.desc": "Log food, hydration, alcohol, exercise, and emotional state. Your coach sees all entries.",
        "help.coachee.section.notes": "Notes",
        "help.coachee.notes.desc": "Bidirectional messages with your coach. Pinned notes stay at the top. Some may be scheduled to appear at specific times.",
        "help.coachee.section.boundaries": "Boundaries",
        "help.coachee.boundaries.desc": "Your safe word mechanism. Use it to pause or fully stop the dynamic. 'RED' (or your custom word) = immediate full stop. Any other word = temporary pause.",
        "help.coachee.section.goals": "Goals",
        "help.coachee.goals.desc": "Propose goals to your coach. They approve, modify, or reject. Track active goals here.",
        "help.coachee.section.journal": "Journal",
        "help.coachee.journal.desc": "Private writing space. Optionally share entries with your coach (checkbox per entry).",
        "help.coachee.section.photos": "Progress Photos",
        "help.coachee.photos.desc": "Upload photos to track visual progress over time. Add captions for context.",
        "help.coachee.section.history": "History & Export",
        "help.coachee.history.desc": "View all past check-ins, tracking logs, and notes. Export everything as JSON for full transparency.",

        # Photo validation
        "photo_validation.title": "Photo Proof Validation",
        "photo_validation.enabled": "AI Photo Validation enabled",
        "photo_validation.disabled": "AI Photo Validation disabled",
        "photo_validation.confidence": "AI Confidence",
        "photo_validation.assessment": "AI Assessment",
        "photo_validation.pending_review": "Pending coach review",
        "photo_validation.validated": "AI validated",
        "photo_validation.rejected": "AI rejected",
        "photo_validation.override": "Coach override",
    },
    "fr": {
        # Navigation
        "nav.tasks": "Tâches",
        "nav.insights": "Analyses",
        "nav.settings": "Paramètres",
        "nav.help": "Aide",
        "nav.logout": "Déconnexion",
        "nav.history": "Historique",
        "nav.export": "Exporter",
        "nav.manage_tasks": "Gérer les tâches",
        "nav.grade_submissions": "Évaluer les soumissions",
        "nav.conditioning": "Conditionnement",
        "nav.rituals": "Rituels",
        "nav.automations": "Automatisations",
        "nav.week_plan": "Planning semaine",
        "nav.onboarding": "Intégration",
        "nav.analyze_text": "Analyser un texte",
        "nav.audit_log": "Journal d'audit",
        "nav.account": "Compte",
        "nav.branding": "Image de marque",
        "nav.support": "Support",
        "nav.admin_panel": "Panneau admin",
        "nav.add_coachee": "+ Ajouter un coaché",
        "nav.language": "Langue",

        # Help page - Coach
        "help.title": "Guide de navigation",
        "help.subtitle": "Où trouver chaque fonctionnalité dans DSCoaching",
        "help.section.dashboard": "Tableau de bord",
        "help.dashboard.desc": "Votre écran d'accueil. Affiche tous vos coachés d'un coup d'œil avec leurs stats : tâches en attente, taux de complétion, note moyenne, série, avertissements, check-ins du jour, score d'engagement et alertes d'inactivité.",
        "help.dashboard.actions": "Actions rapides depuis chaque tuile : envoyer une note, donner un encouragement/avertissement, voir les détails.",
        "help.section.tasks": "Tâches & Assignations",
        "help.tasks.manage": "Gérer les tâches — Créer des modèles (ponctuels, récurrents, de réserve). Assigner à un ou plusieurs coachés. Catégorie, difficulté, date d'échéance.",
        "help.tasks.grade": "Évaluer les soumissions — Évaluer en masse toutes les soumissions en attente. Notes de A à F avec commentaires.",
        "help.tasks.reserve": "Tâches de réserve — Assignées automatiquement si vous n'avez rien envoyé avant l'heure de révélation. Protège votre autorité sans action quotidienne.",
        "help.tasks.recurring": "Tâches récurrentes — Assignation automatique tous les N jours avec variance optionnelle (±25%) pour l'imprévisibilité.",
        "help.tasks.library": "Bibliothèque de tâches — Sauvegardez des modèles. Recherchez et réutilisez entre coachés. Historique d'utilisation visible.",
        "help.tasks.dependencies": "Dépendances — Une tâche ne se débloque qu'après la complétion d'une autre.",
        "help.tasks.photo": "Preuve photo — Les coachés joignent des photos à leurs soumissions. Vous les vérifiez lors de l'évaluation.",
        "help.section.communication": "Communication",
        "help.comm.notes": "Notes — Messages bidirectionnels. Épinglez les importants. Planifiez l'envoi à une heure précise.",
        "help.comm.voice": "Notes vocales — Enregistrez et envoyez de l'audio directement depuis le navigateur.",
        "help.comm.conditioning": "Conditionnement mental — Prompts quotidiens (partagés ou par coaché). Le coaché doit répondre.",
        "help.comm.ack": "Encouragements/Avertissements — Feedback rapide positif/négatif. Affiché en évidence sur le tableau de bord du coaché.",
        "help.section.tracking": "Suivi & Analytique",
        "help.track.checkins": "Check-ins — Entrées structurées matin/soir. Horodatées et immuables.",
        "help.track.logs": "Journaux de suivi — Alimentation, hydratation, alcool, exercice, régulation émotionnelle.",
        "help.track.heatmap": "Heatmap de conformité — Vue calendrier sur 90 jours (vert/jaune/rouge par jour).",
        "help.track.categories": "Ventilation par catégorie — Stats de performance par type de tâche.",
        "help.track.weekly": "Résumé hebdomadaire — Bulletin auto-généré visible par les deux parties.",
        "help.section.coachee_mgmt": "Gestion des coachés",
        "help.mgmt.view": "Vue coaché — Page détaillée : tâches récentes, check-ins, notes, conditionnement, profil, journal, photos, objectifs.",
        "help.mgmt.contract": "Contrat — Éditer les règles et termes (historique versionné). Vous seul pouvez modifier.",
        "help.mgmt.context": "Notes privées — Vos notes privées sur la trajectoire du coaché. Invisibles pour lui/elle.",
        "help.mgmt.features": "Overrides de fonctionnalités — Activer/désactiver des fonctions par coaché.",
        "help.mgmt.profile": "Profil IA — Générer un profil psychologique à partir de toutes les données du coaché.",
        "help.mgmt.safeword": "Safe word — Chaque coaché a un mot d'arrêt configurable. 'RED' = arrêt total. Autre mot = pause.",
        "help.section.automation": "Automatisation",
        "help.auto.rules": "Règles auto — Déclencher des actions sur événements (tâche complétée, manquée, milestone de série).",
        "help.auto.onboarding": "Intégration — Planifier tâches/notes pour les 7 premiers jours d'un nouveau coaché.",
        "help.auto.weekplan": "Planning semaine — Pré-assigner des modèles aux jours de la semaine.",
        "help.section.settings": "Paramètres & Personnalisation",
        "help.settings.account": "Compte — Changer le mot de passe, mettre à jour le nom.",
        "help.settings.branding": "Image de marque — Logo, couleur d'accent, arrière-plan, couleur des cartes. Visible par vos coachés.",
        "help.settings.features": "Bascules de fonctionnalités — Activation/désactivation globale de chaque module.",
        "help.settings.telegram": "Telegram — Token de bot pour notifications push sur les notes et évaluations.",
        "help.section.tools": "Outils",
        "help.tools.analyze": "Analyseur de texte — Collez une conversation ou un texte pour une analyse psychologique par IA.",
        "help.tools.audit": "Journal d'audit — Chaque action enregistrée avec horodatage, IP et user agent.",

        # Help page - Coachee
        "help.coachee.title": "Votre guide",
        "help.coachee.subtitle": "Comment fonctionne votre espace de coaching",
        "help.coachee.section.rules": "Onglet Règles",
        "help.coachee.rules.desc": "Votre contrat et niveau actuel. Affiche votre série, barre de progression vers le niveau suivant, et badges gagnés.",
        "help.coachee.section.checkins": "Check-ins matin & soir",
        "help.coachee.checkins.desc": "Entrées structurées pour commencer et finir votre journée. Incluent une note d'humeur. Immuables une fois soumises — aucune modification possible.",
        "help.coachee.section.tasks": "Tâches",
        "help.coachee.tasks.desc": "Assignations de votre coach. Chaque tâche a une heure limite (freeze time). Complétez avec une réponse texte et une preuve photo optionnelle. Vous pouvez marquer comme partielle si nécessaire.",
        "help.coachee.tasks.streak": "Série — Jours consécutifs avec toutes les tâches complétées à temps. Se remet à zéro à la moindre tâche manquée.",
        "help.coachee.tasks.grades": "Notes — Votre coach évalue de A à F avec commentaires. Visible dans la section des tâches évaluées.",
        "help.coachee.section.conditioning": "Conditionnement mental",
        "help.coachee.conditioning.desc": "Prompts quotidiens de votre coach. Répondez avec soin — ils construisent votre profil psychologique.",
        "help.coachee.section.tracking": "Suivi",
        "help.coachee.tracking.desc": "Enregistrez alimentation, hydratation, alcool, exercice et état émotionnel. Votre coach voit toutes les entrées.",
        "help.coachee.section.notes": "Notes",
        "help.coachee.notes.desc": "Messages bidirectionnels avec votre coach. Les notes épinglées restent en haut. Certaines peuvent être programmées pour apparaître à des heures précises.",
        "help.coachee.section.boundaries": "Limites",
        "help.coachee.boundaries.desc": "Votre mécanisme de safe word. Utilisez-le pour mettre en pause ou arrêter totalement la dynamique. 'RED' (ou votre mot personnalisé) = arrêt immédiat complet. Tout autre mot = pause temporaire.",
        "help.coachee.section.goals": "Objectifs",
        "help.coachee.goals.desc": "Proposez des objectifs à votre coach. Il/elle approuve, modifie ou rejette. Suivez vos objectifs actifs ici.",
        "help.coachee.section.journal": "Journal",
        "help.coachee.journal.desc": "Espace d'écriture privé. Partagez optionnellement des entrées avec votre coach (case à cocher par entrée).",
        "help.coachee.section.photos": "Photos de progression",
        "help.coachee.photos.desc": "Téléchargez des photos pour suivre votre progression visuelle. Ajoutez des légendes pour le contexte.",
        "help.coachee.section.history": "Historique & Export",
        "help.coachee.history.desc": "Consultez tous vos check-ins, journaux de suivi et notes passés. Exportez tout en JSON pour une transparence totale.",

        # Photo validation
        "photo_validation.title": "Validation des preuves photo",
        "photo_validation.enabled": "Validation IA des photos activée",
        "photo_validation.disabled": "Validation IA des photos désactivée",
        "photo_validation.confidence": "Confiance IA",
        "photo_validation.assessment": "Évaluation IA",
        "photo_validation.pending_review": "En attente de vérification par le coach",
        "photo_validation.validated": "Validée par IA",
        "photo_validation.rejected": "Rejetée par IA",
        "photo_validation.override": "Décision du coach",
    },
}
