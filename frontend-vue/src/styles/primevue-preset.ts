import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'

/**
 * Tema de PrimeVue para Dicsys Core: preset Aura con la identidad de la marca.
 *
 * - Esquema claro: paleta Dicsys (azul). Es el que usa cualquier pantalla por defecto.
 * - Esquema oscuro "Blacklist Dark": grafito + bordo. Solo se aplica dentro de un elemento con la
 *   clase `tema-blacklist` (ver darkModeSelector en main.ts).
 *
 * Los colores coinciden con los tokens de Tailwind de main.css (primary / dark / grafito / bordo).
 * Todo ajuste visual comun a los componentes de PrimeVue va aca, no en cada pantalla.
 */
export const DicsysPreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '#e6f4ff',
      100: '#bae3ff',
      200: '#7cc4fa',
      300: '#47a3f3',
      400: '#2186eb',
      500: '#0967d2',
      600: '#0552b5',
      700: '#03449e',
      800: '#01337d',
      900: '#002159',
      950: '#00143a',
    },
    colorScheme: {
      light: {
        surface: {
          0: '#ffffff',
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
          950: '#020617',
        },
        primary: {
          color: '{primary.600}',
          contrastColor: '#ffffff',
          hoverColor: '{primary.700}',
          activeColor: '{primary.800}',
        },
        highlight: {
          background: '{primary.50}',
          focusBackground: '{primary.100}',
          color: '{primary.800}',
          focusColor: '{primary.900}',
        },
      },
      dark: {
        surface: {
          0: '#ffffff',
          50: '#f4f4f6',
          100: '#e4e4e8',
          200: '#cacad1',
          300: '#a8a8b3',
          400: '#8b8b96',
          500: '#5f5f69',
          600: '#45454d',
          700: '#33333a',
          800: '#26262b',
          900: '#1b1b1f',
          950: '#121214',
        },
        // En el esquema oscuro el color de acento pasa a ser el bordo.
        primary: {
          50: '#fff1f2',
          100: '#ffe1e4',
          200: '#ffc8cd',
          300: '#ff9ba5',
          400: '#f8606f',
          500: '#e5364a',
          600: '#c81e35',
          700: '#a3162b',
          800: '#7f1526',
          900: '#5c1220',
          950: '#3a0812',
          color: '{primary.600}',
          contrastColor: '#ffffff',
          hoverColor: '{primary.500}',
          activeColor: '{primary.700}',
        },
        highlight: {
          background: 'color-mix(in srgb, {primary.500}, transparent 84%)',
          focusBackground: 'color-mix(in srgb, {primary.500}, transparent 76%)',
          color: 'rgba(255, 255, 255, 0.92)',
          focusColor: 'rgba(255, 255, 255, 0.92)',
        },
      },
    },
    formField: {
      borderRadius: '0.875rem',
      paddingX: '0.875rem',
      paddingY: '0.625rem',
    },
  },
  components: {
    datatable: {
      colorScheme: {
        light: {
          root: { borderColor: '{surface.100}' },
          headerCell: {
            background: '{surface.50}',
            hoverBackground: '{surface.100}',
            selectedBackground: '{surface.50}',
            color: '{surface.500}',
            hoverColor: '{surface.700}',
            selectedColor: '{primary.700}',
          },
          row: {
            hoverBackground: '#f4f9ff',
            selectedBackground: '{primary.50}',
            selectedColor: '{surface.800}',
          },
        },
        dark: {
          root: { borderColor: '#2b2b31' },
          headerCell: {
            background: '#232328',
            hoverBackground: '{surface.800}',
            selectedBackground: '#232328',
            color: '{surface.400}',
            hoverColor: '{surface.100}',
            selectedColor: '{primary.300}',
          },
          row: {
            background: '{surface.900}',
            stripedBackground: '#202025',
            hoverBackground: '#2a2a30',
            selectedBackground: 'color-mix(in srgb, {primary.600}, {surface.900} 78%)',
            color: '{surface.100}',
            hoverColor: '{surface.0}',
            selectedColor: '{surface.0}',
          },
          bodyCell: { selectedBorderColor: '#2b2b31' },
        },
      },
      headerCell: { padding: '0.875rem 1.5rem' },
      columnTitle: { fontWeight: '700' },
      bodyCell: { padding: '1.125rem 1.5rem' },
      sortIcon: { size: '0.75rem' },
      paginatorBottom: { borderWidth: '0' },
    },
    paginator: {
      root: { padding: '0.875rem 1.5rem', gap: '0.375rem' },
      navButton: {
        width: '2.25rem',
        height: '2.25rem',
        borderRadius: '0.75rem',
        selectedBackground: '{primary.color}',
        selectedColor: '{primary.contrast.color}',
      },
    },
    tag: {
      root: {
        fontSize: '0.75rem',
        fontWeight: '600',
        padding: '0.3125rem 0.75rem',
        gap: '0.4375rem',
      },
    },
    dialog: {
      root: { borderRadius: '1.25rem' },
      header: { padding: '1.5rem' },
      content: { padding: '0 1.5rem 1.5rem 1.5rem' },
      footer: { padding: '0 1.5rem 1.5rem 1.5rem', gap: '0.75rem' },
    },
  },
})
