# Cairn Connectors

**Draft 2. Numbered for markup.**

*Written from a user-need interview, 2026-08-18. Needs were established first; mechanisms were chosen last, and only where a need ranked them. This document designs the v1 slate; the connector rules themselves live in THESIS.md section 8 and are not restated here except where a rule gets sharper. Draft 2 lands the answers to section 8's five questions, received 2026-08-21; the answers are integrated into the body and recorded with their verdicts in section 8.*

---

## 1. Two deployments, never talking

Cairn runs as two completely independent installations, and they will never exchange data.

1. **Work.** A Windows machine, Outlook and the full productivity suite, COM automation available, no Teams or Graph API access. Work content never leaves this machine.
2. **Personal.** A Mac, GSuite for mail and calendar. Personal content stays here.

Each vault gets its own connector configuration, and nothing in this document creates a path between them. The pairing is not synchronized, merged, or migrated; it is two users of the same product who happen to be the same person.

## 2. What the interview established

1. **All four inbound needs are real**: email, calendar, meeting notes, and shared documents all matter daily.
2. **The first connectors are inbound**: email, calendar, and meeting notes together. Reflection refresh and outbound draft staging are explicitly later.
3. **Meeting notes arrive as transcripts.** Copilot recaps at work, Gemini and Meet transcripts on the personal side. This updates the 2026-08-07 sequencing decision, which put self-authored notes first while transcripts sat behind tenant policy: transcripts the user can already export are file-floor content, not something built around policy. A superseding entry goes in DECISIONS.md when this document is ratified.
4. **A read-only Google connector is acceptable.** Named, off by default, pulling only when asked, sending nothing.

## 3. What pointing at a mailbox means

The promise is that Cairn ingests only what you point it at. For single files, pointing is dropping. For a mailbox, the interview settled a plainer reading:

1. **Enabling the connector is the act of pointing.** Turning on the email connector, with its scope visible on the same screen, is the deliberate act.
2. **Every pull is user-invoked.** A palette command or a refresh action fetches; nothing runs on a schedule, and nothing watches for new mail.
3. **Scope is configuration, not ceremony.** Which folders or labels, and how far back, are set once in settings and shown at every pull. No per-message dragging is required.

This is a loosening of the strictest reading, stated openly rather than slipped in: pointing at a mailbox means naming it once and pulling it deliberately, not blessing each message.

## 4. The v1 slate

Each connector declares its domain, direction, and mechanism, ships in this repository, and is off by default. Every pull writes an import report and lands content with convention frontmatter: cut, source, snapshot or received date.

Two rules hold across every connector and the floor alike:

1. **Everything converts to markdown.** Documents, attachments, and transcripts all import automatically as markdown notes; nothing is listed for later selection.
2. **The link to the original source always persists.** When the original arrived as a file, dropped or exported, it is kept as an artifact and the note links to it. When it was pulled, the note links to where it came from. Either way, frontmatter carries a path back to the original, permanently.

### 4.1 Email, inbound

| Deployment | Mechanism | Notes |
| --- | --- | --- |
| Work | Outlook via COM, invoked as a bundled, reviewed script run per pull | No resident process; the script runs, returns, and exits. Message converted to markdown, original kept as artifact. |
| Personal | Google connector, `gmail.readonly` scope, user-invoked pulls | The one network-touching connector on the slate. Tokens stored locally. |
| Floor | .eml files, dragged or exported by hand | Works on any machine with no connector enabled. |

**Default scope: Inbox plus Sent, 90 days back**, visible in settings and in every report. Every pull reads the same window; messages already imported are recognized and skipped, so the one window serves both the initial seed and gap coverage since the last run. A lapse longer than 90 days leaves a gap, and the report says so.

**Setup on the personal side**: the connector spawns the system browser for the OAuth consent flow, and instructions ship for creating a personal OAuth client, honest about the roughly ten-minute setup. Tokens are stored locally. This flow exists on the personal Mac only, for now.

### 4.2 Calendar, inbound

| Deployment | Mechanism | Notes |
| --- | --- | --- |
| Work | Outlook calendar via the same COM path | Events become notes with date, time, subject, and attendees as facts. |
| Personal | Google connector, `calendar.readonly` scope | Same connector, second declared domain. |
| Floor | .ics files | Already in the import floor; nothing new. |

**One note per event.** Encapsulation wins: each event is a self-contained note that cites cleanly and links from anywhere. Cairn maintains no weekly rollup and builds no calendar view, because the calendar application is already good at being a calendar; Cairn holds the facts, and the vault's own calendar tooling can read the dates as they stand.

### 4.3 Meeting transcripts, inbound

Transcripts are format work more than connector work. The importer handles the file shapes transcripts actually arrive in, and the existing connectors carry them where they can.

1. **Formats first**: .docx recaps, .vtt transcripts, and pasted text, each converted with meeting frontmatter (date, source, participants as facts) and the original kept as artifact.
2. **Work**: Copilot recaps leave on a three-rung ladder: copied text first, .docx export second, a network path last. v1 ships the first rung only, so pasted text is the first format the importer must be good at; the later rungs are designed only when reached.
3. **Personal**: Meet transcripts land as Docs in Drive; a `drive.readonly` scope on the Google connector can fetch them, or the file floor carries them.

Distillation rules apply with full force here: decisions, commitments, action items, and open questions come out; affect, tone, and assessments of individuals never do. A transcript is the rawest content Cairn will hold, and the constraint is the reason it can be held at all.

## 5. Explicitly deferred

1. **Reflection refresh** of shared documents and intranet pages. Ranked below inbound by the interview.
2. **Outbound draft staging** into Outlook or Gmail drafts. The design exists in the thesis; it waits until inbound has proven the loop.
3. **Anything resembling Teams or Graph integration.** Unavailable at work by policy, and not needed by the slate above.

## 6. The security ledger

A reviewer should be able to hold this section to the letter.

1. **One connector touches the network**: the Google connector, read-only scopes, user-invoked, personal deployment only. Every other mechanism on the slate is local: COM is inter-process automation on the same machine, and files are files.
2. **No resident processes.** COM scripts run per pull and exit. The Google connector runs inside the plugin only while a pull is in flight.
3. **Send direction: none.** Nothing on the v1 slate can transmit, stage, or dispatch. The first outbound capability arrives with its own design and its own review.

## 7. Gates

1. **Fixture gates per format**: a frozen .eml, .ics, .docx, and .vtt set, converted and asserted byte-for-byte, cold models making that fair.
2. **A scope gate**: a pull against a fixture mailbox imports exactly the configured folders and window, nothing more, and the report says so.
3. **A direction gate**: the Google connector's token scopes are asserted read-only at connect time, and the gate fails if a broader scope is ever requested.

## 8. The five questions, answered 2026-08-21

1. **Default pull scope for email. Ratified as proposed**: Inbox plus Sent, 90 days back, visible in settings and in every report. The window pulls double duty by design: it is the initial seed and it is the gap coverage since the last run.
2. **Attachment policy. Automatic import.** Every document converts to markdown; the original is kept as an artifact when it arrived as a file; and regardless of path, a link to the original source must persist. No selection ceremony.
3. **Copilot recap egress. A ladder: copy, then .docx, then a network path.** v1 starts with copy, so pasted text is the first format the importer must be good at.
4. **Google app registration. Acceptable.** The connector spawns the system browser for the OAuth flow, with shipped instructions for creating a personal client. Personal Mac only, for now.
5. **Calendar depth. Events as individual notes.** Encapsulation is better, and Cairn does not duplicate what the calendar application is already good at.
