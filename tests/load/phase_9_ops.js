import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 50,
  iterations: 1000,
  thresholds: {
    "http_req_failed": ["rate==0"],
    "http_req_duration{endpoint:chat-respond}": ["p(95)<5000"],
    "http_req_duration{endpoint:chat-retrieve}": ["p(95)<500"],
  },
};

const baseUrl = __ENV.AURA_BASE_URL || "http://localhost:8000";
const bearerToken = __ENV.AURA_BEARER_TOKEN || "";
const spaceId = __ENV.AURA_SPACE_ID || "";
const agentName = __ENV.AURA_AGENT_NAME || "load-agent";

function headers() {
  return {
    "Authorization": `Bearer ${bearerToken}`,
    "Content-Type": "application/json",
    "X-Trace-Id": `k6-${__VU}-${__ITER}`,
  };
}

function mustHaveEnv() {
  if (!bearerToken || !spaceId) {
    throw new Error("AURA_BEARER_TOKEN and AURA_SPACE_ID are required.");
  }
}

export default function () {
  mustHaveEnv();
  const selector = Math.random();

  if (selector < 0.6) {
    const response = http.post(
      `${baseUrl}/api/v1/chat/respond`,
      JSON.stringify({
        message: "Riassumi il documento di test in una frase.",
        space_ids: [spaceId],
        stream: false,
      }),
      { headers: headers(), tags: { endpoint: "chat-respond" } },
    );
    check(response, {
      "chat/respond returns 200": (r) => r.status === 200,
      "chat/respond has trace_id": (r) => !!r.json("trace_id"),
    });
  } else if (selector < 0.9) {
    const response = http.post(
      `${baseUrl}/api/v1/chat/retrieve`,
      JSON.stringify({
        query: "policy",
        space_ids: [spaceId],
      }),
      { headers: headers(), tags: { endpoint: "chat-retrieve" } },
    );
    check(response, {
      "chat/retrieve returns 200": (r) => r.status === 200,
    });
  } else {
    const response = http.post(
      `${baseUrl}/api/v1/agents/${agentName}/run`,
      JSON.stringify({
        input: { query: "load test" },
      }),
      { headers: headers(), tags: { endpoint: "agent-run" } },
    );
    check(response, {
      "agent run avoids 5xx": (r) => r.status < 500,
    });
  }

  sleep(0.1);
}
