// LifeGather test site on Cloudflare: a thin Worker in front of the unchanged
// LifeGather image running as a Cloudflare Container. See
// docs/CLOUDFLARE_TEST_SITE.md for setup.
import { Container } from "@cloudflare/containers";
import { accessConfig, verifyAccessToken } from "./access";
import {
  APP_PORT,
  ConfigError,
  TICK_INSTANCE,
  containerEnv,
  forwardRequest,
  instanceName,
  isInternalPath,
  plainResponse,
  tickRequest,
} from "./edge";

export interface Env {
  LIFEGATHER: DurableObjectNamespace<LifeGatherContainer>;
  [setting: string]: unknown;
}

function settings(env: Env): Record<string, string | undefined> {
  const result: Record<string, string | undefined> = {};
  for (const [name, value] of Object.entries(env)) {
    if (typeof value === "string") result[name] = value;
  }
  return result;
}

// First start runs every database migration, which can take a while on an
// empty database; later starts take seconds.
const START_TIMEOUT_MS = 180_000;

export class LifeGatherContainer extends Container<Env> {
  defaultPort = APP_PORT;
  sleepAfter = "5m";
  pingEndpoint = "localhost/health";

  override async fetch(request: Request): Promise<Response> {
    const state = await this.getState();
    if (!this.ctx.container?.running || state.status !== "healthy") {
      try {
        this.envVars = containerEnv(settings(this.env));
      } catch (error) {
        if (error instanceof ConfigError) return plainResponse(503, error.message);
        throw error;
      }
      try {
        await this.startAndWaitForPorts({
          ports: APP_PORT,
          cancellationOptions: {
            portReadyTimeoutMS: START_TIMEOUT_MS,
            instanceGetTimeoutMS: 30_000,
            abort: request.signal,
          },
        });
      } catch (error) {
        console.error("LifeGather container did not become ready", error);
        return plainResponse(503, "LifeGather is starting. Try again in a minute.");
      }
    }
    return this.containerFetch(request, APP_PORT);
  }
}

async function handleVisitor(request: Request, env: Env): Promise<Response> {
  const config = settings(env);
  let access;
  try {
    access = accessConfig(config.ACCESS_TEAM_DOMAIN, config.ACCESS_AUD);
  } catch (error) {
    return plainResponse(503, error instanceof Error ? error.message : "Access is misconfigured");
  }
  if (access) {
    const token = request.headers.get("cf-access-jwt-assertion");
    if (!(await verifyAccessToken(token, access))) {
      return plainResponse(403, "This LifeGather test site needs Cloudflare Access sign-in.");
    }
  } else if (config.ALLOW_WITHOUT_ACCESS !== "true") {
    return plainResponse(
      503,
      "This LifeGather test site is locked until Cloudflare Access is set up " +
        "(ACCESS_TEAM_DOMAIN and ACCESS_AUD).",
    );
  }
  if (isInternalPath(new URL(request.url).pathname)) {
    return plainResponse(404, "Not found");
  }
  const container = env.LIFEGATHER.getByName(instanceName(config));
  return container.fetch(forwardRequest(request));
}

export default {
  fetch(request, env) {
    return handleVisitor(request, env);
  },

  async scheduled(_controller, env) {
    const container = env.LIFEGATHER.getByName(TICK_INSTANCE);
    const response = await container.fetch(tickRequest(settings(env)));
    const summary = await response.text();
    // The tick answers counts only, never account or mailbox content.
    if (!response.ok) {
      throw new Error(`Job tick answered ${response.status}: ${summary.slice(0, 200)}`);
    }
    console.log(`Job tick: ${summary.slice(0, 200)}`);
  },
} satisfies ExportedHandler<Env>;
