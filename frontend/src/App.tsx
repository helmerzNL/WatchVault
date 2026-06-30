import { Route, Routes } from "react-router-dom";
import { useApp } from "./lib/app";
import { Layout } from "./components/Layout";
import { InstallPrompt } from "./components/InstallPrompt";
import { Loading } from "./components/ui";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Overviews } from "./pages/Overviews";
import { Search } from "./pages/Search";
import { Imports } from "./pages/Imports";
import { Profiles } from "./pages/Profiles";
import { Settings } from "./pages/Settings";
import { TitleDetail } from "./pages/TitleDetail";
import { Person } from "./pages/Person";
import { GenreTitles } from "./pages/GenreTitles";
import { useT } from "./lib/i18n";
import { setFormatLocale } from "./lib/format";

export function App() {
  const { ready, user } = useApp();
  const { lang } = useT();
  // Drive written-out date language from the in-app language (not the browser
  // locale). Set during render so the first paint already uses the right
  // language; the setter is an idempotent module-cache write.
  setFormatLocale(lang);

  return (
    <>
      <InstallPrompt />
      {!ready ? (
        <div className="center-screen"><Loading /></div>
      ) : !user ? (
        <Login />
      ) : (
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="/overviews" element={<Overviews />} />
            <Route path="/search" element={<Search />} />
            <Route path="/title/:id" element={<TitleDetail />} />
            <Route path="/person/:id" element={<Person />} />
            <Route path="/genre/:id" element={<GenreTitles />} />
            <Route path="/imports" element={<Imports />} />
            <Route path="/profiles" element={<Profiles />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Dashboard />} />
          </Route>
        </Routes>
      )}
    </>
  );
}
