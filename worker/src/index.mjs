const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function corsHeaders(env) {
  return {
    "access-control-allow-origin": env.ALLOWED_ORIGIN,
    "access-control-allow-headers": "content-type, x-tracker-key",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    vary: "Origin",
  };
}

function json(body, env, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...JSON_HEADERS, ...corsHeaders(env) },
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
  const response = await github(env, `/repos/${env.GITHUB_REPOSITORY}/contents/data/tracker_config.json`);
  const file = await response.json();
  return { config: JSON.parse(decodeBase64(file.content)), sha: file.sha };
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
    if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders(env) });
    if (url.pathname !== "/keywords") return json({ error: "Not found" }, env, 404);

    try {
      if (request.method === "GET") {
        const { config } = await readTrackerConfig(env);
        return json({ keywords: config.keywords || [] }, env);
      }

      if (request.method !== "POST") return json({ error: "Method not allowed" }, env, 405);
      if (request.headers.get("x-tracker-key") !== env.ADMIN_KEY) return json({ error: "동기화키가 맞지 않습니다." }, env, 401);

      const body = await request.json();
      const keywords = normalizeKeywords(body.keywords);
      if (!keywords) return json({ error: "키워드를 1~30개, 각 40자 이하로 입력해 주세요." }, env, 400);

      const { config, sha } = await readTrackerConfig(env);
      config.keywords = keywords;
      await github(env, `/repos/${env.GITHUB_REPOSITORY}/contents/data/tracker_config.json`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          message: "data: update tracked keywords",
          content: encodeBase64(`${JSON.stringify(config, null, 2)}\n`),
          sha,
        }),
      });
      await dispatchMeasurement(env);
      return json({ keywords, measurementQueued: true }, env);
    } catch (error) {
      console.error(error);
      return json({ error: "키워드 파일 저장에 실패했습니다. 잠시 후 다시 시도해 주세요." }, env, 502);
    }
  },
};
