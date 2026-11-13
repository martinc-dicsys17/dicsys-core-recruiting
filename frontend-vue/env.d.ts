/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Origen del frontend Flask actual; solo se usa en desarrollo para los enlaces a pantallas existentes. */
  readonly VITE_LEGACY_ORIGIN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
