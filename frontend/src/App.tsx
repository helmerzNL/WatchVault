import { Route, Routes } from "react-router-dom";
import { useApp } from "./lib/app";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Overviews } from "./pages/Overviews";
import { Search } from "./pages/Search";
import { Imports } from "./pages/Imports";
import { Profiles } from "./pages/Profiles";
import { Settings } from "./pages/Settings";
import { TitleDetail } from "./pages/TitleDetail";

export function App() {
  const { ready, user } = useApp();

  if (!ready) {
    return <div className="center-screen"><Loading label="Starting WatchVault…" /></div>;
  }

  if (!user) {
    return <Login />;
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="/overviews" element={<Overviews />} />
        <Route path="/search" element={<Search />} />
        <Route path="/title/:id" element={<TitleDetail />} />
        <Route path="/imports" element={<Imports />} />
        <Route path="/profiles" element={<Profiles />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Dashboard />} />
      </Route>
    </Routes>
  );
}
