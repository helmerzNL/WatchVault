import { render, type RenderOptions } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AppProvider } from "../lib/app";

interface AppRenderOptions extends Omit<RenderOptions, "wrapper"> {
  initialEntries?: string[];
  routePath?: string;
}

export function renderWithApp(
  element: ReactElement,
  { initialEntries = ["/"], routePath, ...options }: AppRenderOptions = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={initialEntries}>
        <AppProvider>
          {routePath ? <Routes><Route path={routePath} element={children as ReactElement} /></Routes> : children}
        </AppProvider>
      </MemoryRouter>
    );
  }

  return {
    user: userEvent.setup(),
    ...render(element, { wrapper: Wrapper, ...options }),
  };
}
