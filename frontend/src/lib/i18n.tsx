import { useCallback } from "react";
import { useApp } from "./app";
import en, { type Dict } from "../locales/en";
import nl from "../locales/nl";
import fr from "../locales/fr";
import es from "../locales/es";
import it from "../locales/it";
import de from "../locales/de";
import { FlagDE, FlagGB, FlagES, FlagFR, FlagIT, FlagNL } from "../components/flags";
import type { ComponentType, SVGProps } from "react";

export type LangCode = "de" | "en" | "es" | "fr" | "it" | "nl";

export interface Language {
  code: LangCode;
  native: string;   // name in its own language
  english: string;  // name in English (for a11y/labels)
  Flag: ComponentType<SVGProps<SVGSVGElement>>;
}

// Alphabetical by native name: Deutsch, English, Español, Français, Italiano, Nederlands.
export const LANGUAGES: Language[] = [
  { code: "de", native: "Deutsch", english: "German", Flag: FlagDE },
  { code: "en", native: "English", english: "English", Flag: FlagGB },
  { code: "es", native: "Español", english: "Spanish", Flag: FlagES },
  { code: "fr", native: "Français", english: "French", Flag: FlagFR },
  { code: "it", native: "Italiano", english: "Italian", Flag: FlagIT },
  { code: "nl", native: "Nederlands", english: "Dutch", Flag: FlagNL },
];

const DICTS: Record<LangCode, Dict> = { de, en, es, fr, it, nl };

export function langOf(code: string | undefined): LangCode {
  return (LANGUAGES.find((l) => l.code === code)?.code ?? "en") as LangCode;
}

export function translate(lang: string, key: string, vars?: Record<string, unknown>): string {
  const code = langOf(lang);
  const raw = DICTS[code][key] ?? en[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, k) =>
    vars[k] === undefined || vars[k] === null ? `{${k}}` : String(vars[k])
  );
}

export type TFn = (key: string, vars?: Record<string, unknown>) => string;

export function useT(): { t: TFn; lang: LangCode } {
  const { prefs } = useApp();
  const lang = langOf(prefs.language);
  const t = useCallback<TFn>((key, vars) => translate(lang, key, vars), [lang]);
  return { t, lang };
}

// ── Genre localization ────────────────────────────────────────────────────
// Genres are stored canonically in English (keeps stat aggregation stable);
// only their display label is localized. Covers the fixed TMDB genre set.
const GENRES: Record<string, Partial<Record<LangCode, string>>> = {
  "Action": { nl: "Actie", fr: "Action", es: "Acción", it: "Azione", de: "Action" },
  "Adventure": { nl: "Avontuur", fr: "Aventure", es: "Aventura", it: "Avventura", de: "Abenteuer" },
  "Animation": { nl: "Animatie", fr: "Animation", es: "Animación", it: "Animazione", de: "Animation" },
  "Comedy": { nl: "Komedie", fr: "Comédie", es: "Comedia", it: "Commedia", de: "Komödie" },
  "Crime": { nl: "Misdaad", fr: "Crime", es: "Crimen", it: "Crimine", de: "Krimi" },
  "Documentary": { nl: "Documentaire", fr: "Documentaire", es: "Documental", it: "Documentario", de: "Dokumentarfilm" },
  "Drama": { nl: "Drama", fr: "Drame", es: "Drama", it: "Dramma", de: "Drama" },
  "Family": { nl: "Familie", fr: "Familial", es: "Familia", it: "Famiglia", de: "Familie" },
  "Fantasy": { nl: "Fantasy", fr: "Fantastique", es: "Fantasía", it: "Fantasy", de: "Fantasy" },
  "History": { nl: "Historisch", fr: "Histoire", es: "Historia", it: "Storia", de: "Historie" },
  "Horror": { nl: "Horror", fr: "Horreur", es: "Terror", it: "Horror", de: "Horror" },
  "Music": { nl: "Muziek", fr: "Musique", es: "Música", it: "Musica", de: "Musik" },
  "Mystery": { nl: "Mysterie", fr: "Mystère", es: "Misterio", it: "Mistero", de: "Mystery" },
  "Romance": { nl: "Romantiek", fr: "Romance", es: "Romance", it: "Romantico", de: "Liebesfilm" },
  "Science Fiction": { nl: "Sciencefiction", fr: "Science-fiction", es: "Ciencia ficción", it: "Fantascienza", de: "Science Fiction" },
  "TV Movie": { nl: "Tv-film", fr: "Téléfilm", es: "Película de TV", it: "Film TV", de: "TV-Film" },
  "Thriller": { nl: "Thriller", fr: "Thriller", es: "Suspense", it: "Thriller", de: "Thriller" },
  "War": { nl: "Oorlog", fr: "Guerre", es: "Bélica", it: "Guerra", de: "Krieg" },
  "Western": { nl: "Western", fr: "Western", es: "Western", it: "Western", de: "Western" },
  "Action & Adventure": { nl: "Actie & Avontuur", fr: "Action & Aventure", es: "Acción y aventura", it: "Azione e avventura", de: "Action & Abenteuer" },
  "Kids": { nl: "Kinderen", fr: "Enfants", es: "Infantil", it: "Bambini", de: "Kinder" },
  "News": { nl: "Nieuws", fr: "Actualités", es: "Noticias", it: "Notizie", de: "Nachrichten" },
  "Reality": { nl: "Reality", fr: "Téléréalité", es: "Reality", it: "Reality", de: "Reality" },
  "Sci-Fi & Fantasy": { nl: "Sci-Fi & Fantasy", fr: "Sci-Fi & Fantastique", es: "Sci-Fi y fantasía", it: "Sci-Fi e fantasy", de: "Sci-Fi & Fantasy" },
  "Soap": { nl: "Soap", fr: "Feuilleton", es: "Telenovela", it: "Soap", de: "Seifenoper" },
  "Talk": { nl: "Talkshow", fr: "Talk-show", es: "Programa de entrevistas", it: "Talk show", de: "Talk" },
  "War & Politics": { nl: "Oorlog & Politiek", fr: "Guerre & Politique", es: "Guerra y política", it: "Guerra e politica", de: "Krieg & Politik" },
};

export function translateGenre(lang: string, name: string): string {
  const code = langOf(lang);
  if (code === "en") return name;
  return GENRES[name]?.[code] ?? name;
}

export function useGenre(): (name: string) => string {
  const { lang } = useT();
  return useCallback((name: string) => translateGenre(lang, name), [lang]);
}

// ── Provider localization ──────────────────────────────────────────────────
// Provider names are stored non-localized (a single text column), so the labels
// that must read naturally in every language are localized here by key:
//   * generic ("Other")        — Trakt watches with no catalogued network, movies
//   * cinema  ("Bioscoop")     — films seen in the cinema
//   * plex / jellyfin          — shown together as one "Digital Library"
//   * digital_library          — the merged Plex+Jellyfin entry in the stats
export function providerLabel(t: TFn, key: string | undefined, name: string): string {
  if (key === "generic") return t("provider.generic");
  if (key === "cinema") return t("provider.cinema");
  if (key === "plex" || key === "jellyfin" || key === "digital_library")
    return t("provider.digitalLibrary");
  return name;
}

// Same as providerLabel but uses the short "Local" wording for the merged
// Plex+Jellyfin library — used only in the Search screen, where space is tight.
export function providerLabelShort(t: TFn, key: string | undefined, name: string): string {
  if (key === "plex" || key === "jellyfin" || key === "digital_library")
    return t("provider.digitalLibraryShort");
  return providerLabel(t, key, name);
}
