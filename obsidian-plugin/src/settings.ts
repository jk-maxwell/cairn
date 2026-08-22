import { App, PluginSettingTab, Setting } from "obsidian";
import type CairnPlugin from "./main";

export interface CairnSettings {
	baseUrl: string;
}

export const DEFAULT_SETTINGS: CairnSettings = {
	baseUrl: "http://127.0.0.1:8765",
};

export class CairnSettingTab extends PluginSettingTab {
	plugin: CairnPlugin;

	constructor(app: App, plugin: CairnPlugin) {
		super(app, plugin);
		this.plugin = plugin;
	}

	display(): void {
		const { containerEl } = this;
		containerEl.empty();

		containerEl.createEl("h2", { text: "Cairn settings" });

		new Setting(containerEl)
			.setName("Engine base URL")
			.setDesc(
				"Base URL of the local Cairn engine (ask.py). Chat requests are sent to <base>/v1/chat/completions."
			)
			.addText((text) =>
				text
					.setPlaceholder("http://127.0.0.1:8765")
					.setValue(this.plugin.settings.baseUrl)
					.onChange(async (value) => {
						this.plugin.settings.baseUrl =
							value.trim() || DEFAULT_SETTINGS.baseUrl;
						await this.plugin.saveSettings();
					})
			);
	}
}
