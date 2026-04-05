/**
 * Hook handlers for auto-recall, auto-capture, and compaction safety.
 * v0.6.0: Tool-aware auto-capture — captures tool results, not just chat.
 * - Enriched auto-recall (summaries + raw, topK=15, structured context)
 * - Tool-aware auto-capture (captures exec results, API calls, file ops)
 * - after_tool_call hook for high-signal tool results
 * - Smarter compaction (extracts decisions, preferences, key facts)
 */

const NOISE_PATTERNS = [
  /^HEARTBEAT_OK$/i,
  /^NO_REPLY$/i,
  /Read HEARTBEAT\.md/i,
  /nothing needs attention/i,
  /no pending tasks/i,
  /Pre-compaction memory flush/i,
  /gateway (connected|disconnected|restart)/i,
  /WhatsApp gateway (connected|disconnected)/i,
  /systemd service/i,
  /tool schema.*not.*pool_id/i,
  /tool surface cannot/i,
  /^System: \[/i,
];

// Tool results that are just noise — don't store these
const TOOL_NOISE_PATTERNS = [
  /^\(no new output\)/i,
  /^\(no output yet\)/i,
  /^Process still running/i,
  /^Killed session/i,
  /^HEARTBEAT_OK/i,
  /^NO_REPLY/i,
];

// High-signal tools whose results are worth capturing
const HIGH_SIGNAL_TOOLS = [
  "exec",           // Shell commands — deployments, installs, builds
  "web_search",     // Research results
  "web_fetch",      // Page content
  "memory_store",   // Explicit memory stores
  "message",        // Messages sent
  "gateway",        // Config changes
  "sessions_spawn", // Sub-agent tasks
];

// Keywords in tool results that indicate meaningful outcomes
const OUTCOME_KEYWORDS = [
  /(?:deploy|install|build|compil|migrat|updat|upgrad)/i,
  /(?:created|deleted|removed|stopped|started|restarted)/i,
  /(?:error|failed|success|complete|done|fixed)/i,
  /(?:docker|container|image|volume|nginx|postgres|redis)/i,
  /(?:disk|memory|cpu|GB|MB|freed|usage|space)/i,
  /(?:commit|push|merge|branch|release|version)/i,
  /(?:API|endpoint|route|deploy|server|port|health)/i,
  /(?:config|setting|credential|key|token|password)/i,
  /(?:price|cost|\$|paid|invoice|order|purchase)/i,
  /(?:user|customer|account|signup|login)/i,
];

function isObviousNoise(text) {
  return NOISE_PATTERNS.some(p => p.test(text));
}

function isToolNoise(text) {
  return TOOL_NOISE_PATTERNS.some(p => p.test(text?.trim() || ""));
}

function hasOutcomeSignal(text) {
  if (!text || text.length < 30) return false;
  return OUTCOME_KEYWORDS.some(p => p.test(text));
}

/**
 * Extract tool call info from assistant message content blocks.
 * Claude-style messages have content arrays with tool_use blocks.
 */
function extractToolCalls(messages) {
  const toolCalls = [];
  for (const m of messages) {
    if (m.role !== "assistant") continue;
    const content = m.content;
    if (!Array.isArray(content)) continue;
    for (const block of content) {
      if (block.type === "tool_use") {
        toolCalls.push({
          tool: block.name,
          input: block.input,
          id: block.id,
        });
      }
    }
  }
  return toolCalls;
}

/**
 * Extract tool results from message history.
 * Tool results come as role="tool" messages with tool_use_id.
 */
function extractToolResults(messages) {
  const results = [];
  for (const m of messages) {
    if (m.role !== "tool") continue;
    const content = typeof m.content === "string" ? m.content : JSON.stringify(m.content);
    results.push({
      id: m.tool_use_id,
      content,
    });
  }
  return results;
}

/**
 * Build a concise summary of what tools did in this turn.
 * Pairs tool calls with their results for meaningful context.
 */
function summarizeToolActions(messages) {
  const calls = extractToolCalls(messages);
  const results = extractToolResults(messages);
  const resultMap = new Map(results.map(r => [r.id, r.content]));

  const summaries = [];
  for (const call of calls) {
    const result = resultMap.get(call.id) || "";

    // Skip noise results
    if (isToolNoise(result)) continue;

    // Skip low-signal tools unless result has outcome keywords
    if (!HIGH_SIGNAL_TOOLS.includes(call.tool) && !hasOutcomeSignal(result)) continue;

    // Build concise action summary
    let action = `[${call.tool}]`;
    const input = call.input || {};

    // Add relevant context from tool input
    if (call.tool === "exec") {
      action += ` ${(input.command || "").slice(0, 200)}`;
    } else if (call.tool === "web_search") {
      action += ` query: "${input.query || ""}"`;
    } else if (call.tool === "web_fetch") {
      action += ` ${input.url || ""}`;
    } else if (call.tool === "message") {
      action += ` ${input.action || ""} to=${input.target || input.to || ""}`;
    } else if (call.tool === "gateway") {
      action += ` ${input.action || ""}`;
    } else if (call.tool === "Edit" || call.tool === "Write" || call.tool === "Read") {
      action += ` ${input.file_path || input.path || ""}`;
    }

    // Truncate result but keep the meaningful part
    const truncResult = result.length > 500 ? result.slice(0, 400) + "\n...(truncated)" : result;

    if (truncResult && !isToolNoise(truncResult) && hasOutcomeSignal(truncResult)) {
      summaries.push(`${action}\nResult: ${truncResult}`);
    } else if (hasOutcomeSignal(action)) {
      // Even without a meaningful result, the action itself might be worth storing
      summaries.push(action);
    }
  }
  return summaries;
}

export function registerHooks(api, client, config) {

  // ========== ENRICHED AUTO-RECALL ==========
  // Pulls 15 memories, prioritizes summaries + raw over triples,
  // builds structured context block for the agent.
  if (config.autoRecall) {
    api.on("before_agent_start", async (event) => {
      try {
        const lastMsg = event.messages?.filter(m => m.role === "user").pop();
        const query = lastMsg?.content;
        if (!query || typeof query !== "string") return {};

        // Search with higher limit, prefer summaries and raw text
        const results = await client.search(query, 15);
        const allMemories = Array.isArray(results) ? results : results?.results || results?.memories || [];
        if (!allMemories.length) return {};

        // Separate by type — prioritize summaries and raw over triples
        const summaries = [];
        const profiles = [];
        const facts = [];

        for (const m of allMemories) {
          const content = m.memory || m.text || m.content || "";
          const type = m.type || m.memory_type || "";
          if (type === "summary" || type === "raw") {
            summaries.push(content);
          } else if (type === "profile") {
            profiles.push(content);
          } else {
            facts.push(content);
          }
        }

        // Build structured context — summaries first (most context), then profiles, then facts
        const sections = [];

        if (summaries.length) {
          sections.push("Key Context:\n" + summaries.slice(0, 5).map(s => `- ${s}`).join("\n"));
        }
        if (profiles.length) {
          sections.push("User/Agent Info:\n" + profiles.slice(0, 5).map(s => `- ${s}`).join("\n"));
        }
        if (facts.length) {
          sections.push("Related Facts:\n" + facts.slice(0, 5).map(s => `- ${s}`).join("\n"));
        }

        if (!sections.length) return {};

        const context = sections.join("\n\n");

        return {
          prependContext: `<memchip-recall count="${allMemories.length}">\n${context}\n</memchip-recall>`,
        };
      } catch (err) {
        console.error("[memchip] auto-recall error:", err.message);
        return {};
      }
    });
  }

  // ========== TOOL-AWARE AUTO-CAPTURE ==========
  // Captures both conversation content AND tool results.
  // Two hooks: after_tool_call for real-time tool capture,
  // agent_end for full-turn summary with tool context.
  if (config.autoCapture) {

    // Hook 1: after_tool_call — capture high-signal tool results immediately
    api.on("after_tool_call", async (event) => {
      _captureToolCall(client, event).catch(err => {
        console.error("[memchip] tool-capture error:", err.message);
      });
    });

    // Hook 2: agent_end — capture full turn with conversation + tool summaries
    api.on("agent_end", async (event) => {
      _captureAsync(client, event).catch(err => {
        console.error("[memchip] auto-capture error:", err.message);
      });
    });
  }

  // ========== SMARTER COMPACTION ==========
  // Before context is trimmed, extract key decisions, preferences, and facts.
  // This is the last chance to save context before it's lost.
  if (config.compactionFlush) {
    api.on("before_compaction", async (event) => {
      try {
        const msgs = event.messages;
        if (!msgs?.length) return;

        // Extract substantive messages (conversation)
        const substantive = msgs
          .filter(m => m.role === "user" || m.role === "assistant")
          .filter(m => {
            const content = typeof m.content === "string" ? m.content
              : Array.isArray(m.content) ? m.content.filter(b => b.type === "text").map(b => b.text).join("\n")
              : JSON.stringify(m.content);
            return content.length > 80 && !isObviousNoise(content);
          });

        if (substantive.length < 2 && !msgs.some(m => m.role === "tool")) return;

        // Conversation window
        const window = substantive.slice(-20);
        const convText = window
          .map(m => {
            const content = typeof m.content === "string" ? m.content
              : Array.isArray(m.content) ? m.content.filter(b => b.type === "text").map(b => b.text).join("\n")
              : JSON.stringify(m.content);
            return `${m.role}: ${content.slice(0, 500)}`;
          })
          .join("\n");

        // Tool action summaries — critical to capture before compaction
        const toolSummaries = summarizeToolActions(msgs.slice(-40));

        const sections = [];
        if (convText.length > 100) sections.push(convText);
        if (toolSummaries.length) {
          sections.push("Actions performed:\n" + toolSummaries.join("\n\n"));
        }

        if (sections.length) {
          await client.store(sections.join("\n\n---\n\n"), { source: "pre-compaction" });
        }
      } catch (err) {
        console.error("[memchip] compaction flush error:", err.message);
      }
    });
  }
}

// ========== CAPTURE HELPERS ==========

/**
 * Capture high-signal tool results in real-time.
 * Called via after_tool_call hook — fires for every tool call.
 * Only stores results that contain meaningful outcomes.
 */
async function _captureToolCall(client, event) {
  // OpenClaw after_tool_call fires twice per call — once without durationMs, once with.
  // Only capture the final one (with durationMs) to avoid duplicates.
  if (event.durationMs == null) return;

  // OpenClaw after_tool_call event shape: { toolName, params, result, error?, durationMs? }
  const toolName = event.toolName || event.tool;
  const toolInput = event.params;
  const toolResult = event.result;
  if (!toolName || !toolResult) return;

  const resultText = typeof toolResult === "string" ? toolResult : JSON.stringify(toolResult);

  // Skip noise
  if (isToolNoise(resultText)) return;
  if (resultText.length < 30) return;

  // Only capture high-signal tools or results with outcome keywords
  if (!HIGH_SIGNAL_TOOLS.includes(toolName) && !hasOutcomeSignal(resultText)) return;

  // Skip read-only operations that don't change state
  if (toolName === "Read" || toolName === "memory_search" || toolName === "memory_list") return;
  if (toolName === "process" && toolInput?.action === "poll") return;
  if (toolName === "process" && toolInput?.action === "list") return;

  // Must have an actual outcome signal in the result
  if (!hasOutcomeSignal(resultText)) return;

  // Build context string
  let action = `[Tool: ${toolName}]`;
  const input = toolInput || {};

  if (toolName === "exec") {
    action += ` Command: ${(input.command || "").slice(0, 300)}`;
  } else if (toolName === "gateway") {
    action += ` Action: ${input.action || ""}`;
  } else if (toolName === "message") {
    action += ` ${input.action || "send"} to=${input.target || input.to || ""}`;
  } else if (toolName === "Edit" || toolName === "Write") {
    action += ` File: ${input.file_path || input.path || ""}`;
  }

  const truncResult = resultText.length > 600 ? resultText.slice(0, 500) + "\n...(truncated)" : resultText;

  const text = `${action}\nOutcome: ${truncResult}`;

  await client.store(text, { source: "tool-capture", source_ref: `tool:${toolName}` });
}

/**
 * Full-turn capture — conversation text + tool action summaries.
 * Called at agent_end. Builds a richer picture by including what
 * tools did alongside what was said.
 */
async function _captureAsync(client, event) {
  const msgs = event.messages;
  if (!msgs?.length) return;

  // Get recent conversation (user + assistant text)
  const recent = msgs.slice(-12); // Wider window to catch tool context

  const conversationParts = recent
    .filter(m => m.role === "user" || m.role === "assistant")
    .slice(-4)
    .map(m => {
      let content;
      if (typeof m.content === "string") {
        content = m.content;
      } else if (Array.isArray(m.content)) {
        // Extract text blocks only (skip tool_use blocks for conversation capture)
        content = m.content
          .filter(b => b.type === "text")
          .map(b => b.text)
          .join("\n");
      } else {
        content = JSON.stringify(m.content);
      }
      return `${m.role}: ${content}`;
    });

  // Get tool action summaries from this turn
  const toolSummaries = summarizeToolActions(recent);

  // Build combined text
  const sections = [];

  const convText = conversationParts.join("\n");
  if (convText.length > 30 && !isObviousNoise(convText)) {
    sections.push(convText);
  }

  if (toolSummaries.length) {
    sections.push("Actions performed:\n" + toolSummaries.join("\n\n"));
  }

  if (!sections.length) return;

  const text = sections.join("\n\n---\n\n");

  // Don't store if it's all noise
  if (isObviousNoise(text)) return;

  await client.store(text, { source: "auto-capture" });
}
