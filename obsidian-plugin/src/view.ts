import { ItemView, MarkdownRenderer, WorkspaceLeaf } from "obsidian";
import type CairnPlugin from "./main";
import { SSEStreamParser } from "./sseParser";

export const CAIRN_VIEW_TYPE = "cairn-chat-view";

type Role = "user" | "assistant" | "error";

interface ChatMessage {
	role: Role;
	content: string;
}

const LOG_PREFIX = "[cairn]";

export class CairnChatView extends ItemView {
	plugin: CairnPlugin;
	private conversation: ChatMessage[] = [];
	private messagesEl!: HTMLElement;
	private inputEl!: HTMLTextAreaElement;
	private sendBtn!: HTMLButtonElement;
	private abortController: AbortController | null = null;

	constructor(leaf: WorkspaceLeaf, plugin: CairnPlugin) {
		super(leaf);
		this.plugin = plugin;
	}

	getViewType(): string {
		return CAIRN_VIEW_TYPE;
	}

	getDisplayText(): string {
		return "Cairn";
	}

	getIcon(): string {
		return "compass";
	}

	async onOpen(): Promise<void> {
		const root = this.contentEl;
		root.empty();
		root.addClass("cairn-view");

		const header = root.createDiv({ cls: "cairn-header" });
		header.createEl("span", { cls: "cairn-title", text: "Cairn" });
		const newChatBtn = header.createEl("button", {
			cls: "cairn-new-chat",
			text: "New chat",
		});
		newChatBtn.addEventListener("click", () => this.newChat());

		this.messagesEl = root.createDiv({ cls: "cairn-messages" });
		this.renderEmptyState();

		const inputRow = root.createDiv({ cls: "cairn-input-row" });
		this.inputEl = inputRow.createEl("textarea", {
			cls: "cairn-input",
			attr: { placeholder: "Ask your notes…", rows: "3" },
		});
		this.sendBtn = inputRow.createEl("button", {
			cls: "cairn-send mod-cta",
			text: "Send",
		});

		this.inputEl.addEventListener("keydown", (evt: KeyboardEvent) => {
			if (evt.key === "Enter" && !evt.shiftKey) {
				evt.preventDefault();
				this.handleSend();
			}
		});
		this.sendBtn.addEventListener("click", () => this.handleSend());
	}

	async onClose(): Promise<void> {
		this.abortController?.abort();
	}

	private renderEmptyState(): void {
		this.messagesEl.empty();
		this.messagesEl.createDiv({
			cls: "cairn-empty",
			text: "Ask a question about your notes to get started.",
		});
	}

	private newChat(): void {
		this.conversation = [];
		this.abortController?.abort();
		this.renderEmptyState();
		console.log(`${LOG_PREFIX} new chat started`);
	}

	private handleSend(): void {
		const text = this.inputEl.value.trim();
		if (!text) return;
		this.inputEl.value = "";
		void this.sendMessage(text);
	}

	private async sendMessage(text: string): Promise<void> {
		if (this.messagesEl.querySelector(".cairn-empty")) {
			this.messagesEl.empty();
		}

		this.conversation.push({ role: "user", content: text });
		this.renderBubble("user", text);

		const assistantBubble = this.renderBubble("assistant", "");
		const contentEl = assistantBubble.querySelector(
			".cairn-bubble-content"
		) as HTMLElement;
		assistantBubble.addClass("cairn-pending");

		this.setSending(true);

		const baseUrl = this.plugin.settings.baseUrl.replace(/\/+$/, "");
		const url = `${baseUrl}/v1/chat/completions`;
		const body = JSON.stringify({
			model: "cairn",
			messages: this.conversation.map((m) => ({
				role: m.role,
				content: m.content,
			})),
			stream: true,
		});

		this.abortController = new AbortController();
		console.log(`${LOG_PREFIX} request start`, { url });

		let assembled = "";
		try {
			const response = await fetch(url, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body,
				signal: this.abortController.signal,
			});

			if (!response.ok || !response.body) {
				throw new Error(
					`HTTP ${response.status} ${response.statusText}`
				);
			}

			const reader = response.body.getReader();
			const decoder = new TextDecoder("utf-8");
			const parser = new SSEStreamParser();

			while (true) {
				const { value, done } = await reader.read();
				if (done) break;
				const chunk = decoder.decode(value, { stream: true });
				const deltas = parser.feed(chunk);
				for (const delta of deltas) {
					assembled += delta;
					contentEl.empty();
					await MarkdownRenderer.render(
						this.app,
						assembled,
						contentEl,
						"",
						this
					);
					this.messagesEl.scrollTo({
						top: this.messagesEl.scrollHeight,
					});
				}
				if (parser.done) break;
			}

			for (const warning of parser.warnings) {
				console.error(
					`${LOG_PREFIX} malformed SSE payload`,
					warning.payload,
					warning.error
				);
			}

			this.conversation.push({ role: "assistant", content: assembled });
			console.log(`${LOG_PREFIX} request finished`, {
				url,
				chars: assembled.length,
			});
		} catch (err: unknown) {
			if (
				err instanceof DOMException &&
				err.name === "AbortError"
			) {
				console.log(`${LOG_PREFIX} request aborted`, { url });
				return;
			}
			const message = err instanceof Error ? err.message : String(err);
			console.error(`${LOG_PREFIX} request failed`, { url, message });

			assistantBubble.remove();
			this.renderBubble(
				"error",
				`Cairn engine unreachable at ${baseUrl} — is ask.py running?\n\nDetails: ${message}`
			);
		} finally {
			assistantBubble.removeClass("cairn-pending");
			this.setSending(false);
			this.abortController = null;
		}
	}

	private setSending(sending: boolean): void {
		this.sendBtn.disabled = sending;
		this.sendBtn.setText(sending ? "Sending…" : "Send");
	}

	private renderBubble(role: Role, text: string): HTMLElement {
		const bubble = this.messagesEl.createDiv({
			cls: `cairn-bubble cairn-bubble-${role}`,
		});
		bubble.createDiv({ cls: "cairn-bubble-role", text: roleLabel(role) });
		const contentEl = bubble.createDiv({ cls: "cairn-bubble-content" });
		if (text) {
			if (role === "error") {
				contentEl.setText(text);
			} else {
				void MarkdownRenderer.render(
					this.app,
					text,
					contentEl,
					"",
					this
				);
			}
		}
		this.messagesEl.scrollTo({ top: this.messagesEl.scrollHeight });
		return bubble;
	}
}

function roleLabel(role: Role): string {
	switch (role) {
		case "user":
			return "You";
		case "assistant":
			return "Cairn";
		case "error":
			return "Error";
	}
}
