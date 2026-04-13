import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import nl from './locales/nl.json';

export const LANG_STORAGE_KEY = 'docrunr.lang';

export const SUPPORTED_LANGS = ['en', 'nl'] as const;
export type UiLanguage = (typeof SUPPORTED_LANGS)[number];

const resources = {
  en: { translation: en },
  nl: { translation: nl },
};

export function isUiLanguage(value: string): value is UiLanguage {
  return (SUPPORTED_LANGS as readonly string[]).includes(value);
}

function initialLanguage(): string {
  if (typeof window !== 'undefined') {
    try {
      const stored = window.localStorage.getItem(LANG_STORAGE_KEY);
      if (stored && isUiLanguage(stored)) {
        return stored;
      }
    } catch {
      // ignore storage errors (private mode, etc.)
    }
  }
  if (typeof navigator === 'undefined') {
    return 'en';
  }
  const code = navigator.language.split('-')[0]?.toLowerCase();
  return code === 'nl' ? 'nl' : 'en';
}

i18n.use(initReactI18next).init({
  resources,
  lng: initialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export default i18n;
