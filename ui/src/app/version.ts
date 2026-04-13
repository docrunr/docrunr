/** Injected at build time (see vite.config.ts); matches Git tag in release images. */
export const APP_VERSION: string = import.meta.env.VITE_APP_VERSION;
