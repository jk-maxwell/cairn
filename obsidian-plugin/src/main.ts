import { Plugin, WorkspaceLeaf } from "obsidian";
import { CairnSettings, DEFAULT_SETTINGS, CairnSettingTab } from "./settings";
import { CairnChatView, CAIRN_VIEW_TYPE } from "./view";

export default class CairnPlugin extends Plugin {
	settings: CairnSettings = DEFAULT_SETTINGS;

	async onload(): Promise<void> {
		await this.loadSettings();

		this.registerView(
			CAIRN_VIEW_TYPE,
			(leaf) => new CairnChatView(leaf, this)
		);

		this.addRibbonIcon("compass", "Open Cairn chat", () => {
			void this.activateView();
		});

		this.addCommand({
			id: "open-cairn-chat",
			name: "Open Cairn chat",
			callback: () => {
				void this.activateView();
			},
		});

		this.addSettingTab(new CairnSettingTab(this.app, this));

		console.log("[cairn] plugin loaded");
	}

	onunload(): void {
		console.log("[cairn] plugin unloaded");
	}

	async activateView(): Promise<void> {
		const { workspace } = this.app;

		let leaf: WorkspaceLeaf | null = null;
		const existing = workspace.getLeavesOfType(CAIRN_VIEW_TYPE);

		if (existing.length > 0) {
			leaf = existing[0];
		} else {
			leaf = workspace.getRightLeaf(false);
			await leaf?.setViewState({ type: CAIRN_VIEW_TYPE, active: true });
		}

		if (leaf) {
			workspace.revealLeaf(leaf);
		}
	}

	async loadSettings(): Promise<void> {
		this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
	}

	async saveSettings(): Promise<void> {
		await this.saveData(this.settings);
	}
}
