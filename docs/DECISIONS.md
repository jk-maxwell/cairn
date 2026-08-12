# DECISIONS

*Append-only, dated, one line of why per entry. Settled stays settled: an entry here is not re-argued, only superseded by a later dated entry that says so.*

These records were carried over from Cairn's original private build. Entries about the working method used at the time have been dropped as no longer relevant; everything below is a decision about the product itself. Dates are the dates the decisions were actually made.

---

- **2026-07-16. Models as built: `nomic-embed-text` (768 dimensions) for retrieval, a small local instruct model for generation.** Chosen during the proof of concept. A future model swap that changes the embedding dimension now fails loudly via a runtime gate rather than silently corrupting the index.

- **2026-07. Reference information is mirrored faithfully; working information is distilled for purpose.** The distinction is where records obligations attach, and naming the one exception (distilled summaries are themselves working records) keeps the reflection principle honest.

- **2026-07. Distillation never records affect, tone, or assessments of individuals.** Constrained by construction rather than by policy. This also keeps candid personal context permanently outside the collection.

- **2026-08-07. The name is Cairn.** The tool is the trail marker, not the navigator: it is built from what was already there, and it exists so someone can find the way.

- **2026-08-07. The roadmap runs as parallel tracks in thin slices, not sequential milestones.** Gates bind slices, not tracks, so a blocked slice never blocks the rest. The weekly measure is whether Cairn can answer something it could not answer last week.

- **2026-08-07. A third-party chat client is the interface; Cairn is the engine, serving the local-model protocol.** The client thinks it is talking to a model. It is talking to grounded, cited, records-filtered retrieval. Interfaces are swappable; the contract lives in the engine.

- **2026-08-07. Intervention ladder for third-party clients: adopt, configure off, fork and strip, scratch.** Take the cheapest rung that holds and escalate only on demonstrated failure. Forked code keeps its license, and the engine stays separate, which makes the interface boundary a license boundary too.

- **2026-08-07. Surfaces are named Chat, Save, and Prepare.** Save is deliberate, one file at a time, with no ambient watching. That design choice is also the privacy promise: it knows only what you give it.

- **2026-08-07. Prepare outputs optionally write back to the vault, at the user's choice. Chat history is a user toggle,** treated as transitory working material rather than a record by default.

- **2026-08-07. Notes before transcripts.** Self-authored notes are the path into the notes and meetings capability that no platform policy can close. Meeting transcripts sit behind tenant-level policy and are never built around.

- **2026-08-07. The preflight suite is also the speedometer.** A frozen benchmark prompt, never edited for the same reason a survey question is never edited, runs cold and warm on every preflight and logs time to first token, total time, and tokens per second. Model comparisons become data rather than impressions. A leak gate fails loudly if the generation model reasons out loud.

- **2026-08-07. Generation model chosen on measured evidence, not reputation.** Two traps recorded for anyone repeating the exercise: some model tags are thinking-family builds that leak deliberation even when thinking is disabled, so prefer instruct builds that are non-thinking by construction; and the model library may require an explicit quantization suffix, so a bare tag can silently not exist.

- **2026-08-07. The protocol surface serves both dialects, OpenAI-compatible and Ollama-compatible.** One engine, two shapes, roughly sixty extra lines. Chat clients differ in which dialect they speak, and serving both means the choice of interface can never be blocked by a wire format.

- **2026-08-07. On the protocol face, the client's system prompt, sampling settings, and model choice are discarded, not merged.** The interface is chrome, and chrome cannot edit the grounding contract. This is also the injection defence: text inside a document that a client echoes back as a system message cannot tell Cairn to stop citing or to answer from training memory. Structurally impossible rather than merely prohibited, because only the question string and the retrieved rows cross into synthesis.

- **2026-08-07. Citations and the strength label ride inside the answer text on the protocol face.** The protocol carries only a string, so the no-receipt-no-answer rule survives contact with third-party chrome only if the receipt is part of the payload.

- **2026-08-07. Protocol multi-turn is explicitly not implemented: the question is the last user message, earlier turns are dropped, and the drop is logged.** Conversation as context is a tracked slice of its own. Silently concatenating turns would have made the engine answer from something other than retrieved evidence.

- **2026-08-07. A CORS allowlist guards the protocol endpoints.** The service already binds to the loopback interface, but a web page open in a browser on the same machine is also a local process. The allowlist means an unknown origin gets no grant and cannot read answers.

- **2026-08-07. The map gains a truth gate: it must name the models the code actually uses, read from the code at check time.** The existence check catches unmapped files; this catches a map that lies about mapped ones. Motivated by real drift found by hand once, and now mechanical.

- **2026-08-10. A deterministic front door sits in front of retrieval: chatter, holdings, capability, ask.** A greeting cost 96 seconds, five irrelevant passages, and two paragraphs of narrated reasoning before the refusal. The first three lanes are decided by whole-string matching against a checked-in vocabulary and answered with no embedding and no model call. Whole-string matching rather than keywords, because the expensive error is a real question intercepted by a canned reply, so the default is always the retrieval path.

- **2026-08-10. Warmth is template text; answers are evidence.** Every word on the chatter and capability lanes is authored and checked into the repository, and every number on the holdings lane is read from the database at answer time. Nothing on a front-door lane is generated, so nothing there can make an unsupported claim about the corpus. This is the boundary that keeps personable from becoming ungrounded.

- **2026-08-10. Front-door replies still carry a receipt, and it says retrieval was not run.** The no-receipt-no-answer rule is satisfied by an honest statement that no evidence was consulted, never by omitting the line. A user must always be able to tell which sentences stand on saved material.

- **2026-08-10. A no-hope distance floor skips the generation model, separate from the weak label and provisional.** Weak still deserves an answer; the floor means nothing is there at all. Set between the only two observed points at the time, and every firing is logged with its distance so daily use recalibrates it from data. Refusals above the floor carry the nearest headings retrieval actually returned, so a dead end becomes a trail marker at no extra cost.

- **2026-08-10. The refusal must be bare, enforced by equality rather than containment.** The previous gate only checked that the refusal string was present, which a narrated refusal satisfied while reading as hedging. The gate now asserts the whole reply equals the refusal sentence. The prompt gained an explicit no-preamble rule, but the gate, not the prompt, is what tells us whether it worked.

- **2026-08-10. The frozen benchmark carries a frozen copy of the system prompt.** It previously imported the live prompt, so editing the grounding contract silently changed the measured payload and made new rows incomparable with old ones. The benchmark measures generation speed under a constant load; the contract itself is measured by the grounding gates, which is where it belongs.

- **2026-08-10. Phantom citations are labelled in the open, not suppressed and not retried.** A live answer cited six passages against five, and nothing noticed. Every assembled answer is now scanned for bracketed indices above the evidence count, the violation is logged as a warning, and a visible note tells the reader which citations do not exist and to treat claims resting on them as unsupported. Suppression was rejected because it hides the defect from the only person able to judge it. A retry was rejected because it doubles a latency that is already the first thing users complain about.

- **2026-08-10. The grounding contract has three cases, not two.** It previously defined only "passages relate, so answer" and "nothing relates, so refuse". A live failure was neither: the passages were genuinely on topic and genuinely silent on the specific question, and with no defined shape for that case the model improvised and invented a passage number. Case two now says: at most three sentences, state that the material does not address the specific question, state what the passages do cover, cite each by number, do not speculate, and do not use the refusal sentence. Forcing the refusal here was rejected because "I hold related material and it is silent on this" is more useful than a flat no.

- **2026-08-10. The citation range rule is stated in the contract as well as enforced in code.** The prompt names the ceiling explicitly, and the gate proves it held. Prompt and gate are deliberately redundant: the prompt is what usually prevents the defect, the gate is what proves it was prevented, and neither is trusted alone.
