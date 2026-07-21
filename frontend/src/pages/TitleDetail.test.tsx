import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../lib/api";
import { expectNoA11yViolations } from "../test/a11y";
import { renderWithApp } from "../test/render";
import { TitleDetail } from "./TitleDetail";

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  upload: vi.fn(),
}));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: apiMock };
});

vi.mock("../lib/branding", () => ({
  applyBrandIcons: vi.fn(),
  applyBrandManifest: vi.fn(),
}));

const baseUser = {
  id: "user-1",
  display_name: "Synthetic Viewer",
  is_admin: false,
  household_id: "household-1",
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

const title = {
  id: "title-1",
  title: "Synthetic Film",
  kind: "movie",
  year: 2026,
  overview: "A deterministic fixture.",
  release_date: "2026-01-01",
  genres: [],
  networks: [],
  tags: [],
  watch_dates: [],
  cast: [],
  crew: [],
  events: [],
};

function mockApi(permissions: string[]) {
  apiMock.get.mockImplementation((path: string, options?: { profile?: string }) => {
    if (path === "/auth/status") {
      return Promise.resolve({ bootstrapped: true, user: { ...baseUser, permissions } });
    }
    if (path === "/preferences") return Promise.resolve(preferences);
    if (path === "/profiles") return Promise.resolve([{ ...baseUser, events: 0 }]);
    if (path === "/search/title/title-1") {
      return Promise.resolve({
        ...title,
        title: options?.profile === "user-1" ? "Synthetic Film" : "Initial Film",
      });
    }
    if (path === "/providers") return Promise.resolve([]);
    return Promise.reject(new Error(`Unexpected GET ${path}`));
  });
}

describe("TitleDetail watch mutation", () => {
  beforeEach(() => {
    apiMock.post.mockResolvedValue({ status: "ok" });
  });

  it("does not expose watch mutation without ingest.write", async () => {
    mockApi(["catalog.read"]);
    const { container } = renderWithApp(<TitleDetail />, {
      initialEntries: ["/titles/title-1"],
      routePath: "/titles/:id",
    });
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(/Film$/);
    expect(screen.queryByRole("button", { name: "Mark as watched" })).not.toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("posts the exact scoped date payload once and reports success", async () => {
    mockApi(["catalog.read", "ingest.write"]);
    const { user } = renderWithApp(<TitleDetail />, {
      initialEntries: ["/titles/title-1"],
      routePath: "/titles/:id",
    });
    await screen.findByRole("heading", { name: "Synthetic Film" });
    await screen.findByRole("option", { name: "Auto (network)" });
    fireEvent.click(screen.getByRole("button", { name: "Mark as watched" }));
    await user.click(await screen.findByRole("button", { name: "Today" }));

    await waitFor(() => expect(apiMock.post).toHaveBeenCalledTimes(1));
    expect(apiMock.post).toHaveBeenCalledWith("/titles/title-1/watch", {
      user_id: "user-1",
      date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    });
    expect(await screen.findByText("Watch date added")).toBeInTheDocument();
  });

  it("surfaces ApiError feedback without reporting success", async () => {
    mockApi(["catalog.read", "ingest.write"]);
    apiMock.post.mockRejectedValueOnce(new ApiError(409, "Already watched"));
    const { user } = renderWithApp(<TitleDetail />, {
      initialEntries: ["/titles/title-1"],
      routePath: "/titles/:id",
    });
    await screen.findByRole("heading", { name: "Synthetic Film" });
    await screen.findByRole("option", { name: "Auto (network)" });
    fireEvent.click(screen.getByRole("button", { name: "Mark as watched" }));
    await user.click(await screen.findByRole("button", { name: "Today" }));
    expect(await screen.findByText("Already watched")).toBeInTheDocument();
    expect(screen.queryByText("Watch date added")).not.toBeInTheDocument();
  });
});
