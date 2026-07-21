import { screen, waitFor } from "@testing-library/react";
import { Outlet } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { expectNoA11yViolations } from "./test/a11y";
import { renderWithApp } from "./test/render";

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  upload: vi.fn(),
}));

vi.mock("./lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./lib/api")>();
  return { ...actual, api: apiMock };
});

vi.mock("./lib/branding", () => ({
  applyBrandIcons: vi.fn(),
  applyBrandManifest: vi.fn(),
}));

vi.mock("./components/InstallPrompt", () => ({
  InstallPrompt: () => null,
}));

vi.mock("./components/Layout", () => ({
  Layout: () => (
    <div>
      <header>Authenticated shell</header>
      <main><Outlet /></main>
    </div>
  ),
}));

vi.mock("./pages/Dashboard", () => ({
  Dashboard: () => <h1>Dashboard destination</h1>,
}));
vi.mock("./pages/Overviews", () => ({ Overviews: () => <h1>Overviews destination</h1> }));
vi.mock("./pages/Search", () => ({ Search: () => <h1>Search destination</h1> }));
vi.mock("./pages/Imports", () => ({ Imports: () => <h1>Imports destination</h1> }));
vi.mock("./pages/Profiles", () => ({ Profiles: () => <h1>Profiles destination</h1> }));
vi.mock("./pages/Settings", () => ({ Settings: () => <h1>Settings destination</h1> }));
vi.mock("./pages/TitleDetail", () => ({ TitleDetail: () => <h1>Title destination</h1> }));
vi.mock("./pages/Person", () => ({ Person: () => <h1>Person destination</h1> }));
vi.mock("./pages/GenreTitles", () => ({ GenreTitles: () => <h1>Genre destination</h1> }));

const user = {
  id: "user-1",
  display_name: "Synthetic Viewer",
  is_admin: false,
  household_id: "household-1",
  household_name: "Test Household",
  permissions: ["catalog.read"],
};

const preferences = {
  theme: "system",
  accent: "#0a84ff",
  default_profile: "user-1",
  language: "en",
  expert: false,
  cinemaAdd: true,
  dashboard_layout: { order: [], hidden: [] },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function mockAuthenticatedApi() {
  apiMock.get.mockImplementation((path: string) => {
    if (path === "/auth/status") return Promise.resolve({ bootstrapped: true, user });
    if (path === "/preferences") return Promise.resolve(preferences);
    if (path === "/profiles") return Promise.resolve([{ ...user, events: 4 }]);
    return Promise.reject(new Error(`Unexpected GET ${path}`));
  });
}

describe("App authentication and routing", () => {
  beforeEach(() => {
    vi.stubGlobal("PublicKeyCredential", class PublicKeyCredential {});
  });

  it("shows the loading state until authentication resolves", async () => {
    const status = deferred<{ bootstrapped: boolean; user: null }>();
    apiMock.get.mockImplementation((path: string) => {
      if (path === "/auth/status") return status.promise;
      return Promise.reject(new Error(`Unexpected GET ${path}`));
    });

    const { container } = renderWithApp(<App />);

    expect(screen.getByText("Loading…")).toBeInTheDocument();
    await expectNoA11yViolations(container);

    status.resolve({ bootstrapped: true, user: null });
    expect(await screen.findByRole("button", { name: "Sign in with passkey" })).toBeEnabled();
  });

  it("renders the unauthenticated login gate accessibly", async () => {
    apiMock.get.mockResolvedValue({ bootstrapped: true, user: null });

    const { container } = renderWithApp(<App />);

    expect(await screen.findByRole("button", { name: "Sign in with passkey" })).toBeEnabled();
    expect(screen.getByText("WatchVault")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it.each([
    ["/", "Dashboard destination"],
    ["/search", "Search destination"],
    ["/not-a-real-route", "Dashboard destination"],
  ])("renders the authenticated destination for %s", async (path, destination) => {
    mockAuthenticatedApi();

    const { container } = renderWithApp(<App />, { initialEntries: [path] });

    expect(await screen.findByRole("heading", { name: destination })).toBeInTheDocument();
    expect(screen.getByText("Authenticated shell")).toBeInTheDocument();
    await waitFor(() => expect(apiMock.get).toHaveBeenCalledWith("/preferences"));
    await expectNoA11yViolations(container);
  });
});
