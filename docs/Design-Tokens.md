# Design tokens de Dicsys Core

Fuente de verdad visual del frontend. Hoy viven inline en el `tailwind.config` de
`frontend/modulos/core/templates/core/base.html` (Tailwind 3 por Play CDN, pineado a 3.4.17).
Este archivo los documenta para que la SPA (Tailwind 4, `@theme`) reproduzca la misma
identidad sin mirar el template legacy. Si cambia el `base.html`, cambia este archivo.

## Colores

| Token | Valor | Uso |
|---|---|---|
| `primary-50` | `#E6F4FF` | fondos suaves |
| `primary-100` | `#BAE3FF` | |
| `primary-200` | `#7CC4FA` | |
| `primary-300` | `#47A3F3` | |
| `primary-400` | `#2186EB` | |
| `primary-500` | `#0967D2` | color de marca, botones, links, `glow` |
| `primary-600` | `#0552B5` | hover |
| `primary-700` | `#03449E` | |
| `primary-800` | `#01337D` | |
| `primary-900` | `#002159` | |
| `accent-green` | `#7CB342` | estados positivos |
| `accent-yellow` | `#FDD835` | avisos |
| `accent-orange` | `#FB8C00` | alertas |
| `accent-purple` | `#8E24AA` | |
| `accent-cyan` | `#00ACC1` | |
| `dark-50` … `dark-900` | `#F8FAFC`, `#F1F5F9`, `#E2E8F0`, `#CBD5E1`, `#94A3B8`, `#64748B`, `#475569`, `#334155`, `#1E293B`, `#0F172A` | escala de grises (idéntica a `slate` de Tailwind); `dark-900` es el sidebar |

## Tipografía

- Familia `sans`: `"Plus Jakarta Sans", "Inter", system-ui, sans-serif`.
- Google Fonts: `Plus+Jakarta+Sans:wght@400;500;600;700;800` con `display=swap`.

## Sombras

| Token | Valor |
|---|---|
| `shadow-soft` | `0 2px 15px -3px rgba(0,0,0,0.07), 0 10px 20px -2px rgba(0,0,0,0.04)` |
| `shadow-glow` | `0 0 20px rgba(9,103,210,0.3)` |
| `shadow-inner-glow` | `inset 0 1px 0 0 rgba(255,255,255,0.1)` |

## Animaciones

| Token | Valor |
|---|---|
| `animate-fade-in` | `fadeIn 0.5s ease-out` — `opacity 0 → 1` |
| `animate-slide-up` | `slideUp 0.5s ease-out` — `opacity 0 → 1`, `translateY(10px) → 0` |
| `animate-pulse-slow` | `pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite` |

## Equivalente en Tailwind 4 (`@theme`) para la SPA

```css
@import "tailwindcss";

@theme {
  --color-primary-50: #E6F4FF;
  --color-primary-100: #BAE3FF;
  --color-primary-200: #7CC4FA;
  --color-primary-300: #47A3F3;
  --color-primary-400: #2186EB;
  --color-primary-500: #0967D2;
  --color-primary-600: #0552B5;
  --color-primary-700: #03449E;
  --color-primary-800: #01337D;
  --color-primary-900: #002159;

  --color-accent-green: #7CB342;
  --color-accent-yellow: #FDD835;
  --color-accent-orange: #FB8C00;
  --color-accent-purple: #8E24AA;
  --color-accent-cyan: #00ACC1;

  --color-dark-50: #F8FAFC;
  --color-dark-100: #F1F5F9;
  --color-dark-200: #E2E8F0;
  --color-dark-300: #CBD5E1;
  --color-dark-400: #94A3B8;
  --color-dark-500: #64748B;
  --color-dark-600: #475569;
  --color-dark-700: #334155;
  --color-dark-800: #1E293B;
  --color-dark-900: #0F172A;

  --font-sans: "Plus Jakarta Sans", "Inter", system-ui, sans-serif;

  --shadow-soft: 0 2px 15px -3px rgb(0 0 0 / 0.07), 0 10px 20px -2px rgb(0 0 0 / 0.04);
  --shadow-glow: 0 0 20px rgb(9 103 210 / 0.3);
  --shadow-inner-glow: inset 0 1px 0 0 rgb(255 255 255 / 0.1);

  --animate-fade-in: fadeIn 0.5s ease-out;
  --animate-slide-up: slideUp 0.5s ease-out;
  --animate-pulse-slow: pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite;

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  @keyframes slideUp {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
}
```

## Fuera de alcance de este archivo

- La página pública de certificados (`innovacion/certificate_public.html`) tiene su propio
  `tailwind.config` inline con fuentes `Inter` y `Playfair Display`. Se rediseña cuando pase a
  FastAPI + Jinja (plan v2-final, F12), no forma parte del tema de la SPA.
- Componentes: los patrones de tabla, formulario y modal del legacy no son tokens; se
  reconstruyen con la librería de componentes elegida en F08.
