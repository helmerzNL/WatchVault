import { expect, type Page, type Route } from "@playwright/test";
import {
  BASE_MONTHLY_TITLE,
  BASE_PREFERENCES,
  BASE_SUMMARY,
  FIXED_DATE,
  FIXED_MONTH,
  FIXED_NOW,
  PROFILE,
  PROVIDER,
  SEARCH_RESULT,
  TITLE,
  TITLE_ID,
  USER_ID,
} from "./data";

type Theme = "dark" | "light";

type FixtureState = {
  watchDates: string[];
  mutationBodies: unknown[];
};

export type ApiFixture = {
  state: FixtureState;
  unhandled: string[];
  assertNoUnhandled(): void;
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function parseBody(route: Route): unknown {
  const body = route.request().postData();
  if (body === null) return undefined;
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}

export async function installApiFixture(page: Page, theme: Theme): Promise<ApiFixture> {
  const state: FixtureState = { watchDates: [], mutationBodies: [] };
  const unhandled: string[] = [];
  const expectedMutation = { user_id: USER_ID, date: FIXED_DATE };

  await page.addInitScript(({ now }) => {
    const OriginalDate = Date;
    const fixed = new OriginalDate(now).valueOf();
    class FixedDate extends OriginalDate {
      constructor(...args: ConstructorParameters<typeof Date>) {
        super(...(args.length === 0 ? [fixed] : args));
      }
      static now() {
        return fixed;
      }
    }
    Object.defineProperty(window, "Date", { value: FixedDate });
    const style = document.createElement("style");
    style.textContent = "*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}";
    document.documentElement.appendChild(style);
  }, { now: FIXED_NOW });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    if (url.origin !== "http://127.0.0.1:7212") {
      unhandled.push(`${method} ${url.href}`);
      await route.abort("blockedbyclient");
      return;
    }

    if (!url.pathname.startsWith("/api/")) {
      await route.continue();
      return;
    }

    const path = url.pathname.slice(4);
    const key = `${method} ${path}`;

    if (key === "GET /auth/status") {
      return json(route, { bootstrapped: true, user: PROFILE });
    }
    if (key === "GET /profiles") return json(route, [PROFILE]);
    if (key === "GET /preferences") {
      return json(route, { ...BASE_PREFERENCES, theme });
    }
    if (key === "GET /providers") return json(route, [PROVIDER]);
    if (key === "GET /tags") return json(route, [{ id: "tag-reference", name: "Reference" }]);
    if (key === "GET /search/facets") {
      return json(route, { genres: ["Drama"], years: [2026] });
    }
    if (key === "GET /search") {
      return json(route, { results: [SEARCH_RESULT], total: 1 });
    }
    if (key === `GET /search/title/${TITLE_ID}`) {
      return json(route, { ...TITLE, watch_dates: [...state.watchDates] });
    }
    if (key === "GET /stats/summary") {
      const watched = state.watchDates.length;
      return json(route, {
        ...BASE_SUMMARY,
        totals: {
          ...BASE_SUMMARY.totals,
          hours: BASE_SUMMARY.totals.hours + watched * 2,
        },
        this_month: {
          hours: BASE_SUMMARY.this_month.hours + watched * 2,
          events: BASE_SUMMARY.this_month.events + watched,
        },
        events: [
          ...BASE_SUMMARY.events,
          ...state.watchDates.map((date) => ({ date, count: 1 })),
        ],
      });
    }
    if (key === "GET /stats/providers") {
      return json(route, [{ provider: PROVIDER.id, name: PROVIDER.name, hours: 2, events: 1 }]);
    }
    if (key === "GET /stats/recent") {
      return json(route, [
        { date: "2026-07-14", count: 1 },
        ...state.watchDates.map((date) => ({ date, count: 1 })),
      ]);
    }
    if (key === "GET /stats/unknown") return json(route, []);
    if (key === "GET /stats/month") {
      const watchedTitle = state.watchDates.length
        ? [{ ...TITLE, watched_at: state.watchDates[0], provider: PROVIDER.id }]
        : [];
      expect(url.searchParams.get("month")).toBe(FIXED_MONTH);
      return json(route, [BASE_MONTHLY_TITLE, ...watchedTitle]);
    }
    if (key === "POST /titles/enrich-missing") {
      const body = parseBody(route);
      const ids = typeof body === "object" && body !== null && "ids" in body
        ? (body as { ids?: unknown }).ids
        : undefined;
      const allowed = ["title-existing-film", TITLE_ID];
      if (
        !Array.isArray(ids)
        || ids.length === 0
        || ids.some((id) => typeof id !== "string" || !allowed.includes(id))
      ) {
        unhandled.push(`${key} ${JSON.stringify(body)}`);
        return json(route, { error: "Unexpected enrichment body" }, 422);
      }
      return json(route, { queued: ids.length });
    }
    if (key === `POST /titles/${TITLE_ID}/watch`) {
      const body = parseBody(route);
      state.mutationBodies.push(body);
      if (JSON.stringify(body) !== JSON.stringify(expectedMutation)) {
        unhandled.push(`${key} ${JSON.stringify(body)}`);
        return json(route, { error: "Unexpected watch mutation body" }, 422);
      }
      state.watchDates = [FIXED_DATE];
      return json(route, { ok: true, date: FIXED_DATE });
    }

    unhandled.push(`${key} ${JSON.stringify(parseBody(route))}`);
    await route.abort("blockedbyclient");
  });

  return {
    state,
    unhandled,
    assertNoUnhandled() {
      expect(unhandled, "Every browser request must be declared by the API fixture").toEqual([]);
    },
  };
}
