import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { FIXED_DATE, TITLE_ID, USER_ID } from "./fixtures/data";
import { installApiFixture, type ApiFixture } from "./fixtures/api";

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

async function prepare(page: Page, testInfo: TestInfo) {
  const theme = testInfo.project.name.endsWith("-light") ? "light" : "dark";
  const fixture = await installApiFixture(page, theme);
  await page.goto("/");
  return fixture;
}

async function runReferenceJourney(
  page: Page,
  testInfo: TestInfo,
  withScreenshots: boolean,
): Promise<ApiFixture> {
  const fixture = await prepare(page, testInfo);
  const navSelector = testInfo.project.name.includes("-mobile-") ? ".tabbar" : ".nav-links";

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expectAccessible(page);
  if (withScreenshots) await expect(page).toHaveScreenshot("01-dashboard.png", { fullPage: true });

  const searchNav = page.locator(`${navSelector} a[href="/search"]`);
  await searchNav.focus();
  await expect(searchNav).toBeFocused();
  await searchNav.press("Enter");
  await expect(page.getByRole("heading", { name: "Search" })).toBeVisible();
  const search = page.getByRole("searchbox");
  await search.focus();
  await expect(search).toBeFocused();
  await search.fill("Synthetic Film");
  await expect(page.getByRole("link", { name: /Synthetic Film/ })).toBeVisible();
  await expectAccessible(page);
  if (withScreenshots) await expect(page).toHaveScreenshot("02-search.png", { fullPage: true });

  await page.getByRole("link", { name: /Synthetic Film/ }).click();
  await expect(page).toHaveURL(new RegExp(`/title/${TITLE_ID}$`));
  await expect(page.getByRole("heading", { name: "Synthetic Film" })).toBeVisible();
  await expectAccessible(page);
  if (withScreenshots) await expect(page).toHaveScreenshot("03-title.png", { fullPage: true });

  await page.getByRole("button", { name: "Mark as watched" }).click();
  await page.getByRole("button", { name: "Today" }).click();
  await expect.poll(() => fixture.state.watchDates).toEqual([FIXED_DATE]);
  expect(fixture.state.mutationBodies).toEqual([{ user_id: USER_ID, date: FIXED_DATE }]);

  const dashboardNav = page.locator(`${navSelector} a[href="/"]`);
  await dashboardNav.focus();
  await expect(dashboardNav).toBeFocused();
  await dashboardNav.press("Enter");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Synthetic Film/ })).toBeVisible();
  await expect(page.locator(".toast")).toBeHidden();
  await expectAccessible(page);
  if (withScreenshots) {
    await expect(page).toHaveScreenshot("04-dashboard-after-watch.png", { fullPage: true });
  }

  fixture.assertNoUnhandled();
  return fixture;
}

test("fixture contract fails closed for an unknown API request", async ({ page }, testInfo) => {
  const fixture = await prepare(page, testInfo);
  const response = await page.evaluate(async () => {
    try {
      await fetch("/api/not-declared");
      return "resolved";
    } catch {
      return "rejected";
    }
  });

  expect(response).toBe("rejected");
  expect(fixture.unhandled).toEqual(["GET /not-declared undefined"]);
});

test("dashboard to watch history reference journey @smoke", async ({ page }, testInfo) => {
  await runReferenceJourney(page, testInfo, false);
});

test("reference journey visual checkpoints", async ({ page }, testInfo) => {
  await runReferenceJourney(page, testInfo, true);
});
