const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function corsHeaders(env, request) {
  const allowedOrigins = String(env.ALLOWED_ORIGINS || "").split(",").map((value) => value.trim());
  const origin = request.headers.get("origin") || "";
  return {
    "access-control-allow-origin": allowedOrigins.includes(origin) ? origin : allowedOrigins[0],
    "access-control-allow-headers": "content-type, x-tracker-key",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    vary: "Origin",
  };
}

function json(body, env, status = 200, request) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...JSON_HEADERS, ...corsHeaders(env, request) },
  });
}

function decodeBase64(value) {
  const bytes = Uint8Array.from(atob(value.replace(/\n/g, "")), (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function encodeBase64(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function normalizeKeywords(value) {
  if (!Array.isArray(value)) return null;
  const unique = [];
  for (const item of value) {
    const keyword = String(item || "").trim().replace(/\s+/g, " ");
    if (!keyword || keyword.length > 40 || unique.includes(keyword)) continue;
    unique.push(keyword);
  }
  return unique.length && unique.length <= 30 ? unique : null;
}

async function github(env, path, init = {}) {
  const response = await fetch(`https://api.github.com${path}`, {
    ...init,
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "user-agent": "gpttest-keyword-sync-worker",
      ...init.headers,
    },
  });
  if (!response.ok) throw new Error(`GitHub API 요청 실패 (${response.status})`);
  return response;
}

async function readTrackerConfig(env) {
  return readRepositoryJson(env, "data/tracker_config.json");
}

async function readRepositoryJson(env, path) {
  const response = await github(env, `/repos/${env.GITHUB_REPOSITORY}/contents/${path}`);
  const file = await response.json();
  return { config: JSON.parse(decodeBase64(file.content)), sha: file.sha };
}

async function writeRepositoryJson(env, path, value, sha, message) {
  await github(env, `/repos/${env.GITHUB_REPOSITORY}/contents/${path}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      message,
      content: encodeBase64(`${JSON.stringify(value, null, 2)}\n`),
      sha,
    }),
  });
}

function normalizeActivity(value) {
  const text = String(value?.text || "").trim().replace(/\s+/g, " ");
  const kind = String(value?.kind || "note");
  if (!text || text.length > 300 || !["mission_complete", "feedback", "note"].includes(kind)) return null;
  return { text, kind };
}

async function dispatchMeasurement(env) {
  await github(env, `/repos/${env.GITHUB_REPOSITORY}/dispatches`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ event_type: "tracker-config-updated" }),
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders(env, request) });
    if (!["/keywords", "/activity"].includes(url.pathname)) return json({ error: "Not found" }, env, 404, request);

    try {
      if (url.pathname === "/activity") {
        const { config, sha } = await readRepositoryJson(env, "data/activity_logs.json");
        const logs = Array.isArray(config.logs) ? config.logs : [];
        if (request.method === "GET") return json({ logs }, env, 200, request);
        if (request.method !== "POST") return json({ error: "Method not allowed" }, env, 405, request);
        if (request.headers.get("x-tracker-key") !== env.ADMIN_KEY) return json({ error: "동기화키가 맞지 않습니다." }, env, 401, request);

        const activity = normalizeActivity(await request.json());
        if (!activity) return json({ error: "기록 내용을 확인해 주세요." }, env, 400, request);
        const nextLogs = [{ id: crypto.randomUUID(), recorded_at: new Date().toISOString(), ...activity }, ...logs].slice(0, 200);
        await writeRepositoryJson(env, "data/activity_logs.json", { schema_version: 1, logs: nextLogs }, sha, "data: add activity log");
        return json({ logs: nextLogs }, env, 200, request);
      }

      if (request.method === "GET") {
        const { config } = await readTrackerConfig(env);
        return json({ keywords: config.keywords || [], primaryKeyword: config.primary_keyword, keywordAddedAt: config.keyword_added_at || {} }, env, 200, request);
      }

      if (request.method !== "POST") return json({ error: "Method not allowed" }, env, 405, request);
      if (request.headers.get("x-tracker-key") !== env.ADMIN_KEY) return json({ error: "동기화키가 맞지 않습니다." }, env, 401, request);

      const body = await request.json();
      const keywords = normalizeKeywords(body.keywords);
      if (!keywords) return json({ error: "키워드를 1~30개, 각 40자 이하로 입력해 주세요." }, env, 400, request);

      const { config, sha } = await readTrackerConfig(env);
      config.keywords = keywords;
      const requestedPrimary = String(body.primaryKeyword || "").trim();
      config.primary_keyword = requestedPrimary === ""
        ? ""
        : (keywords.includes(requestedPrimary) ? requestedPrimary : (keywords.includes(config.primary_keyword) ? config.primary_keyword : ""));
      const previousDates = config.keyword_added_at || {};
      const now = new Date().toISOString();
      config.keyword_added_at = Object.fromEntries(keywords.map((keyword) => [keyword, previousDates[keyword] || now]));
      await writeRepositoryJson(env, "data/tracker_config.json", config, sha, "data: update tracked keywords");
      await dispatchMeasurement(env);
      return json({ keywords, primaryKeyword: config.primary_keyword, keywordAddedAt: config.keyword_added_at, measurementQueued: true }, env, 200, request);
    } catch (error) {
      console.error(error);
      return json({ error: "키워드 파일 저장에 실패했습니다. 잠시 후 다시 시도해 주세요." }, env, 502, request);
    }
  },
};
