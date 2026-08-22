#!/usr/bin/env node
// Smoke test for the Cairn plugin's SSE parser and (optionally) a live
// engine round trip. Run with: node scripts/smoke.mjs
//
// The parser lives in src/sseParser.ts (TypeScript, zero Obsidian deps).
// We transpile it in-memory with esbuild so this test exercises the exact
// same source that gets bundled into main.js - no duplicated logic.

import esbuild from "esbuild";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const parserPath = path.join(__dirname, "..", "src", "sseParser.ts");

async function loadParserModule() {
	const source = await readFile(parserPath, "utf-8");
	const { code } = await esbuild.transform(source, {
		loader: "ts",
		format: "esm",
		target: "es2018",
	});
	const dataUrl = "data:text/javascript;base64," + Buffer.from(code).toString("base64");
	return import(dataUrl);
}

function assert(condition, message) {
	if (!condition) {
		throw new Error(`ASSERTION FAILED: ${message}`);
	}
}

async function testCannedFixtureWholeChunks(SSEStreamParser) {
	const fixture = [
		`data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n`,
		`data: {"choices":[{"delta":{"content":"lo, "}}]}\n\n`,
		`data: {"choices":[{"delta":{"content":"world"}}]}\n\n`,
		`data: {"choices":[{"delta":{"content":"! [1]"}}]}\n\n`,
		`data: [DONE]\n\n`,
	].join("");

	const parser = new SSEStreamParser();
	const deltas = parser.feed(fixture);
	const assembled = deltas.join("");

	assert(assembled === "Hello, world! [1]", `expected reassembled text, got: ${JSON.stringify(assembled)}`);
	assert(parser.done === true, "expected parser.done to be true after [DONE]");
	console.log("  ok: whole-fixture feed reassembles correctly ->", JSON.stringify(assembled));
}

async function testChunkBoundarySplitMidLine(SSEStreamParser) {
	// Simulate a network chunk boundary landing in the middle of a `data:` line
	// and in the middle of a JSON payload - the parser must buffer correctly.
	const full = `data: {"choices":[{"delta":{"content":"Citations: [Note A], strength: high"}}]}\n\n` +
		`data: [DONE]\n\n`;

	const splitPoints = [5, 17, 40, 63, full.length - 3];
	let assembled = "";
	let prev = 0;
	const parser = new SSEStreamParser();
	for (const point of splitPoints) {
		const chunk = full.slice(prev, point);
		prev = point;
		for (const delta of parser.feed(chunk)) {
			assembled += delta;
		}
	}
	for (const delta of parser.feed(full.slice(prev))) {
		assembled += delta;
	}

	assert(
		assembled === "Citations: [Note A], strength: high",
		`expected reassembled text with citations preserved, got: ${JSON.stringify(assembled)}`
	);
	assert(parser.done === true, "expected parser.done to be true after split-chunk [DONE]");
	console.log("  ok: mid-line chunk splits reassemble correctly ->", JSON.stringify(assembled));
}

async function testMalformedPayloadIsWarnedNotThrown(SSEStreamParser) {
	const fixture = `data: {not valid json\n\ndata: {"choices":[{"delta":{"content":"still works"}}]}\n\ndata: [DONE]\n\n`;
	const parser = new SSEStreamParser();
	const deltas = parser.feed(fixture);
	assert(deltas.join("") === "still works", "expected parser to skip malformed line and continue");
	assert(parser.warnings.length === 1, "expected exactly one warning for the malformed payload");
	console.log("  ok: malformed payload produces a warning instead of throwing");
}

async function liveEngineSmoke(SSEStreamParser, baseUrl) {
	console.log(`\nLive engine detected at ${baseUrl} - running streaming round trip ("hello")...`);
	const res = await fetch(`${baseUrl}/v1/chat/completions`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			model: "cairn",
			messages: [{ role: "user", content: "hello" }],
			stream: true,
		}),
	});

	if (!res.ok || !res.body) {
		console.log(`  live smoke SKIPPED: HTTP ${res.status} ${res.statusText}`);
		return;
	}

	const reader = res.body.getReader();
	const decoder = new TextDecoder("utf-8");
	const parser = new SSEStreamParser();
	let assembled = "";

	while (true) {
		const { value, done } = await reader.read();
		if (done) break;
		const chunk = decoder.decode(value, { stream: true });
		for (const delta of parser.feed(chunk)) {
			assembled += delta;
		}
		if (parser.done) break;
	}

	console.log("  live reply assembled (" + assembled.length + " chars):");
	console.log("  " + assembled.slice(0, 500).replace(/\n/g, "\n  "));
}

async function main() {
	const { SSEStreamParser } = await loadParserModule();

	console.log("Running Cairn SSE parser smoke tests...");
	await testCannedFixtureWholeChunks(SSEStreamParser);
	await testChunkBoundarySplitMidLine(SSEStreamParser);
	await testMalformedPayloadIsWarnedNotThrown(SSEStreamParser);
	console.log("All canned-fixture smoke tests passed.\n");

	const baseUrl = process.env.CAIRN_BASE_URL || "http://127.0.0.1:8765";
	try {
		const modelsRes = await fetch(`${baseUrl}/v1/models`, {
			signal: AbortSignal.timeout(1500),
		});
		if (modelsRes.ok) {
			await liveEngineSmoke(SSEStreamParser, baseUrl);
		} else {
			console.log(`No live engine at ${baseUrl} (HTTP ${modelsRes.status}) - skipping live smoke test.`);
		}
	} catch (err) {
		console.log(`No live engine reachable at ${baseUrl} (${err.message}) - skipping live smoke test.`);
	}
}

main().catch((err) => {
	console.error(err);
	process.exit(1);
});
