# Proposed DECISIONS entries — 2026-08-29

*Proposals, not records. Nothing here is in force. Mark up the wording; on your
ratification each accepted entry is appended verbatim to `docs/DECISIONS.md` and
this file is deleted. The ratified document is never edited silently.*

Entries 1–6 are the six owed from the 2026-08-29 design session. Entry 7 records
a ruling made after that session and was not on the original list.

**Ratification status:** entries 3 and 5 were ratified with amendments on
2026-09-02 (see `DECISIONS.md`, entries dated 2026-09-02); their text below is
replaced by a stub so the numbering the evidence appendix relies on stays true.
Entries 1, 2, 4, 6, and 7 remain proposals awaiting a ruling.

Where a proposal supersedes or amends a standing entry, it says so in its own
text, because `DECISIONS.md` is append-only and a later entry is the only way an
earlier one changes.

---

## 1. Obsidian-native expression

> **2026-08-29. Cairn models its data in the encodings Obsidian already
> understands, so the expression costs nothing to build.** Where a choice exists
> between a representation Cairn must render and one the vault renders on its
> own, the native one wins: entity references as wikilinks, entity metadata as
> front-matter properties, multi-valued relations as property lists. The test is
> whether removing Cairn leaves the structure legible and navigable in a plain
> Obsidian install, and the payoff is that the graph view, backlinks panel,
> autocomplete, unlinked-mention detection, Properties editor and Bases queries
> are all obtained without writing any of them. This is already true by accident
> in one place — `ratify()` writes Obsidian's own `aliases:` key, so every alias
> the registry captures has been improving the vault's native search and
> autocomplete all along — and the decision is to make it the rule rather than
> the accident. The consequence Cairn accepts in exchange: it never builds a
> registry front end, because the front end is the Properties panel, and a
> structure edit made there is picked up by `scan_vault()` like any other.

*Not proposed, deliberately:* replacing the governance queue note with ghost
(unresolved) wikilinks. The idea is real — writing `[[Entity]]` for a page that
does not exist produces Obsidian's native "referenced but not real" state, and
ratification becomes clicking the ghost — but it came from a single exploratory
consultation, no panel has scrutinised it, and it would replace a mechanic that
currently works. Deferred by your ruling of 2026-08-29.

## 2. Structure is never inferred from prose

> **2026-08-29. Structure is never initialised by scanning the corpus.** The
> onboarding path may ask, and may propose what the user's own answers imply, but
> it may not read the document pile and infer a starting registry from it —
> there is too much variance in how people write for the inference to be right
> often enough to be worth the correction burden it creates. This sharpens the
> 2026-08-22 decision that structure is user-authored: that entry governed what
> the engine may do with structure at steady state, while this one closes the
> cold-start loophole, where the temptation to bootstrap from prose is strongest
> and a wrong guess is most expensive, because a user with no structure yet has
> no basis to judge what the machine proposed.

## 3. Playbooks are interview lenses, not starter kits

*Ratified 2026-09-02 with amendments (lens persists on the deployment;
position-weighted lenses depend on entry 4 landing; first slice is government +
executive). Text moved to `DECISIONS.md`; stub kept for numbering.*

## 4. Amendment to the registry decision: `organization`, `role`, and typed relations

> **2026-08-29. The registry gains `organization` and `role` as entity types, and
> relations become wikilink-valued front-matter properties. Amends the 2026-08-22
> registry decision, which named `project` and `person` only.** There is one
> `organization` type carrying a `relationship:` property, not a family of types
> for customer, vendor, agency and regulator: those are descriptions of a party's
> relationship to the user rather than intrinsic kinds, the same organization is
> commonly several of them at once, and separate types would fragment alias
> matching across them. `role` is a first-class type rather than a string on a
> person page, because a string cannot carry more than one concurrent role, nor
> tenure, nor the history of who held the role before. Containment is expressed
> by a `parent:` property holding a wikilink, never by nesting folders: folders
> would make every reorganisation a file move, and `_registry_pages()` scans each
> type folder non-recursively, so a nested page would silently stop being part of
> the registry. `parent:` means containment only; ownership, sponsorship and
> reporting are separate relations if they are ever needed. Judgments such as
> priority stay front matter on the entity, ratified through the existing
> checkbox mechanic, and do not become pages of their own — a judgment with its
> own page is the beginning of a task system, which THESIS section 7 says Cairn
> does not build. Cut from this slice: `policy` (statutes are reflections of
> external records, not registry entities), `commitment` (already homed in the
> tasks ledger), and `meeting-series` (deferred, no demand yet). Standing
> concerns and programmes need no new type; they are `project` with
> `status: standing`.
>
> Implementation note carried with this decision: entity types must become data
> in all three places that currently hardcode two — the folder map, the
> governance-queue section parser and its by-type grouping, and the vault scan —
> because a type system that is data in one place and literal in the other two is
> not a type system.

**Your ruling of 2026-08-29, incorporated above:** one `relationship:` key shared
by person and organization pages, not two distinct keys. The mechanic is the same
in both cases and only the vocabulary differs, so a second key would split one
idea across two names for no gain.

## 5. Relationship vocabulary is playbook-supplied, and relations are proposable

*Ratified 2026-09-02 with one amendment (vocabulary is read from the
deployment's persisted playbook, so enrichment-time relation proposals use the
same lens the interview did). Text moved to `DECISIONS.md`, including the
recorded reversal of the assistant's hand-authored-only recommendation; stub
kept for numbering.*

## 6. The affect prohibition becomes a universal setting, and stops claiming to be structural

> **2026-08-29. The prohibition on recording affect, tone and assessments of
> individuals becomes a universal setting, default on, with an opt-out that
> warns plainly. Amends the 2026-07 entry, which described the rule as
> constrained by construction rather than by policy.** The rule applies to every
> deployment and every playbook — it is not a property of the lens the user
> picked, because the reasons for it do not vary by profession. What changes is
> the honesty of the description. A rule with a switch is policy, whichever way
> the switch is shipped, and the 2026-07 phrasing "constrained by construction
> rather than by policy" must not survive this entry: it claims the prohibition
> is structurally impossible to violate at exactly the moment a setting makes it
> possible. The prohibition itself is restated in THESIS section 5 and RATIONALE
> 8.6, both of which present it as admitting no exception; this entry amends them
> to that extent. Default on, because the protection is worth
> more than the capability; opt-out available, because a user who has understood
> the warning is entitled to their own vault.
>
> Standing gap this entry does not close: the distillation system prompt in
> `enrich.py` contains no affect prohibition of any kind, so the rule is today
> documented in three places and implemented in none. The setting is not built
> either. This entry ratifies the intent; the implementation is owed separately
> and should not be reported as done because the decision was recorded.

## 7. Connection surfacing stays a ratified-tier proposal; Generate is the roadmap gap

> **2026-08-29. Connection surfacing does not become Cairn's organising thesis;
> it remains a proposal type on the existing governance machinery, and the
> unbuilt half of the validated loop is Generate.** The proposal to reorder the
> product around surfacing connections between notes was examined and withdrawn.
> RATIONALE 5.1 already names what earns the daily open — import, distil,
> generate — and the reordering would have replaced a loop with an argument for
> it with one that has never been tested. The cognitive-load direction runs the
> wrong way: distil-then-generate hands the user a result, while a surfaced
> connection hands them two notes and the work of seeing why they matter. The
> cold-start claim ran backwards too, since connections need corpus density
> precisely when a new user has none. What survives is narrow and keeps its
> place: a connection may be raised as a ratified-tier proposal, must assert a
> named relation rather than a similarity score, may appear only inside a surface
> the user opened for another reason, and is subject to a kill threshold fixed
> before it ships. The underlying instinct that prompted the proposal is not
> withdrawn and is recorded here as standing: Ask alone does not make anyone want
> Cairn daily, and RATIONALE 1.3's "permissions, not desires" remains the open
> problem. The answer is Generate, which sits unbuilt in Horizon 2 while Distil
> is already built in `enrich.py` — the gap is in the roadmap's execution, not in
> the thesis.

---

## Evidence standing behind these proposals

Recorded so a later reader can weigh them, and so nothing above is taken as
better established than it is.

- Entries 4 and 7 were each put to a four-model consensus panel. Entry 7's panel
  was unanimous against the pivot, including the model assigned to argue for it.
- Entry 7 was additionally tested against the real corpus: an all-pairs cosine
  over the 36 embedded chunks, excluding same-document pairs, returned boilerplate
  in every one of its top four results and no insight. That test ran with no
  filters, so it falsifies the naive form of connection surfacing only; the
  filtered design described in the entry was not tested and is not testable at a
  corpus of three documents.
- Entries 1, 3 and the ghost-link note came from exploratory consultation, not a
  consensus panel, and carry correspondingly less weight.
- Claims relayed by those panels about other PKM products and their retention
  outcomes were asserted without sources and have not been verified. They are
  not repeated in any proposal above and should not be repeated elsewhere.
