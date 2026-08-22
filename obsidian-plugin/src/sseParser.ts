/**
 * Incremental parser for OpenAI-compatible SSE chat-completion streams.
 *
 * The engine sends lines of the form:
 *   data: {"choices":[{"delta":{"content":"..."}}]}
 * terminated eventually by:
 *   data: [DONE]
 *
 * This module has zero dependency on Obsidian or the DOM so it can be
 * exercised directly under plain Node (see scripts/smoke.mjs).
 */

export interface CairnDeltaPayload {
	choices?: Array<{
		delta?: { content?: string };
		finish_reason?: string | null;
	}>;
}

export type SSEWarning = { payload: string; error: unknown };

/**
 * Stateful line-buffering SSE parser. Feed it raw chunks of text as they
 * arrive from a ReadableStream; it returns any complete content deltas
 * found in that chunk, tolerating lines split across chunk boundaries.
 */
export class SSEStreamParser {
	private buffer = "";
	private _done = false;
	private _warnings: SSEWarning[] = [];

	get done(): boolean {
		return this._done;
	}

	/** Malformed `data:` payloads encountered so far, for diagnostics. */
	get warnings(): SSEWarning[] {
		return this._warnings;
	}

	/**
	 * Feed a raw chunk of text. Returns the array of content-delta strings
	 * (possibly empty) extracted from any complete lines now available.
	 */
	feed(chunk: string): string[] {
		this.buffer += chunk;
		const deltas: string[] = [];

		let newlineIndex: number;
		while ((newlineIndex = this.buffer.indexOf("\n")) !== -1) {
			const rawLine = this.buffer.slice(0, newlineIndex);
			this.buffer = this.buffer.slice(newlineIndex + 1);

			const line = rawLine.trim();
			if (line === "" || line.startsWith(":")) {
				// Blank line (event separator) or SSE comment - ignore.
				continue;
			}
			if (!line.startsWith("data:")) {
				continue;
			}

			const payload = line.slice("data:".length).trim();
			if (payload === "[DONE]") {
				this._done = true;
				continue;
			}

			try {
				const json = JSON.parse(payload) as CairnDeltaPayload;
				const content = json?.choices?.[0]?.delta?.content;
				if (typeof content === "string" && content.length > 0) {
					deltas.push(content);
				}
			} catch (error) {
				this._warnings.push({ payload, error });
			}
		}

		return deltas;
	}

	/** Any bytes left in the internal buffer that never resolved to a full line. */
	get pendingBuffer(): string {
		return this.buffer;
	}
}
