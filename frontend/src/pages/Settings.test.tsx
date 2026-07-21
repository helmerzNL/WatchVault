import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoA11yViolations } from "../test/a11y";
import { renderWithApp } from "../test/render";
import { Settings } from "./Settings";

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

const user = {
  id: "user-1",
  display_name: "Synthetic Viewer",
  is_admin: false,
  household_id: "household-1",
  household_name: "Test Household",
  permissions: ["catalog.read", "ingest.write"],
};

const profile = {
  id: "user-1",
  display_name: "Synthetic Viewer",
  is_admin: false,
  events: 4,
};

const initialPreferences = {
  theme: "system",
  accent: "#0a84ff",
  default_profile: "user-1",
  language: "en",
  expert: false,
  cinemaAdd: true,
  dashboard_layout: { order: [], hidden: [] },
};

describe("Settings preferences", () => {
  beforeEach(() => {
    apiMock.get.mockImplementation((path: string) => {
      if (path === "/auth/status") return Promise.resolve({ bootstrapped: true, user });
      if (path === "/preferences") return Promise.resolve(initialPreferences);
      if (path === "/profiles") return Promise.resolve([profile]);
      return Promise.reject(new Error(`Unexpected GET ${path}`));
    });
    apiMock.put.mockImplementation((_path: string, patch: Record<string, unknown>) =>
      Promise.resolve({ ...initialPreferences, ...patch }),
    );
    document.documentElement.removeAttribute("data-theme");
  });

  it("applies light, dark, and system themes through saved preferences", async () => {
    const { user: actor } = renderWithApp(<Settings />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();

    await actor.click(screen.getByRole("button", { name: "Dark" }));
    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "dark"));
    expect(apiMock.put).toHaveBeenLastCalledWith("/preferences", { theme: "dark" });

    await actor.click(screen.getByRole("button", { name: "Light" }));
    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "light"));
    expect(apiMock.put).toHaveBeenLastCalledWith("/preferences", { theme: "light" });

    await actor.click(screen.getByRole("button", { name: "System" }));
    await waitFor(() => expect(document.documentElement).not.toHaveAttribute("data-theme"));
    expect(apiMock.put).toHaveBeenLastCalledWith("/preferences", { theme: "system" });
  });

  it("saves profile and boolean preferences with keyboard interaction", async () => {
    const { user: actor } = renderWithApp(<Settings />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();

    const profileSelect = screen.getByRole("combobox");
    await actor.selectOptions(profileSelect, "all");
    expect(apiMock.put).toHaveBeenCalledWith("/preferences", { default_profile: "all" });

    await actor.tab();
    const offButtons = screen.getAllByRole("button", { name: "Off" });
    offButtons[0].focus();
    await actor.keyboard("{Enter}");
    expect(apiMock.put).toHaveBeenCalledWith("/preferences", { cinemaAdd: false });
  });

  it("has no detectable accessibility violations in the settings sample", async () => {
    const { container } = renderWithApp(<Settings />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
