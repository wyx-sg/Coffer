import animate from "tailwindcss-animate";

// One colour role -> `rgb(var(--role) / <alpha-value>)`, so `bg-surface-raised`
// and `bg-danger/10` both resolve against the theme's channel values in
// src/index.css.
const role = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
// The design tokens (Foundations boards on the design canvas) live as CSS
// variables in src/index.css, per theme; this file only names them for
// Tailwind. No `darkMode` key: the theme is swapped by re-pointing the
// variables under <html data-theme="dark">, so no component ever carries a
// `dark:` utility.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        // --- Foundations roles ------------------------------------------
        surface: {
          DEFAULT: role("surface"),
          sidebar: role("surface-sidebar"),
          raised: role("surface-raised"),
          sunken: role("surface-sunken"),
          selected: role("surface-selected"),
          hover: role("surface-hover"),
          footer: role("surface-footer"),
        },
        border: {
          DEFAULT: role("border"),
          subtle: role("border-subtle"),
        },
        text: {
          DEFAULT: role("text"),
          muted: role("text-muted"),
          subtle: role("text-subtle"),
        },
        accent: {
          DEFAULT: role("accent"),
          foreground: role("on-accent"),
          soft: role("accent-soft"),
          text: role("accent-text"),
        },
        success: { DEFAULT: role("success"), soft: role("success-soft") },
        warning: {
          DEFAULT: role("warning"),
          soft: role("warning-soft"),
          foreground: role("on-warning"),
        },
        danger: {
          DEFAULT: role("danger"),
          soft: role("danger-soft"),
          strong: role("danger-strong"),
        },
        neutral: { DEFAULT: role("neutral"), soft: role("neutral-soft") },
        "on-accent": role("on-accent"),
        "on-status": role("on-status"),
        chip: role("chip"),
        "control-off": role("control-off"),
        knob: role("knob"),
        code: role("code"),
        "focus-ring": role("focus-ring"),
        scrim: "var(--scrim)",

        // --- shadcn aliases (index.css points each at a role) -------------
        input: role("input"),
        ring: role("ring"),
        background: role("background"),
        foreground: role("foreground"),
        primary: { DEFAULT: role("primary"), foreground: role("primary-foreground") },
        secondary: { DEFAULT: role("secondary"), foreground: role("secondary-foreground") },
        destructive: {
          DEFAULT: role("destructive"),
          foreground: role("destructive-foreground"),
        },
        muted: { DEFAULT: role("muted"), foreground: role("muted-foreground") },
        popover: { DEFAULT: role("popover"), foreground: role("popover-foreground") },
        card: { DEFAULT: role("card"), foreground: role("card-foreground") },
        status: { ok: role("status-ok"), warn: role("status-warn"), err: role("status-err") },
        // Find-in-preview match colours; RGB channels so `/opacity` works.
        highlight: {
          DEFAULT: role("highlight"),
          active: role("highlight-active"),
        },
      },
      // Radii grow with the surface: 4 for the smallest marks, 7 for every
      // control, 12 for what floats over the page.
      borderRadius: {
        xs: "4px",
        sm: "5px",
        item: "6px",
        md: "7px",
        lg: "8px",
        xl: "10px",
        "2xl": "12px",
      },
      // The type roles. The app runs on 13px; hierarchy comes from weight and
      // colour, not size jumps. `base` is body too, so an unclassed block and a
      // `text-base` one read the same.
      fontSize: {
        "2xs": ["11px", { lineHeight: "14px" }], // label: group labels, table heads, chips
        xs: ["12px", { lineHeight: "16px" }], // meta: help, status words, mono
        sm: ["13px", { lineHeight: "19px" }], // body and controls
        base: ["13px", { lineHeight: "19px" }],
        md: ["15px", { lineHeight: "20px" }], // dialog and empty-state titles
        lg: ["18px", { lineHeight: "24px", letterSpacing: "-0.01em" }], // page title
        xl: ["20px", { lineHeight: "26px", letterSpacing: "-0.01em" }], // detail title
        display: ["32px", { lineHeight: "36px", letterSpacing: "-0.02em" }], // brand only
      },
      fontWeight: {
        book: "450", // idle nav items and tabs
        label: "550", // buttons, row titles, current nav, field labels
        bold: "650", // page / detail / dialog titles, agent badges
        heavy: "700", // count badges, display
      },
      fontFamily: {
        sans: ['"Figtree"', "system-ui", "-apple-system", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        overlay: "var(--shadow-overlay)",
        lifted: "var(--shadow-lifted)",
        knob: "var(--shadow-knob)",
        focus: "var(--shadow-focus)",
      },
      transitionDuration: {
        fast: "120ms",
        base: "180ms",
        slow: "240ms",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.2, 0, 0, 1)",
        in: "cubic-bezier(0.4, 0, 1, 1)",
        standard: "cubic-bezier(0.4, 0, 0.2, 1)",
      },
      opacity: {
        disabled: "0.45",
        "field-disabled": "0.6",
      },
      zIndex: {
        sticky: "10",
        menu: "40",
        dialog: "50",
        toast: "60",
        tooltip: "70",
      },
      // Fixed component geometry from the Foundations size tokens.
      spacing: {
        "control-sm": "26px",
        "control-md": "30px",
        "control-lg": "36px",
        row: "40px",
        "setting-row": "56px",
        sidebar: "220px",
        rail: "56px",
      },
      maxWidth: {
        prose: "60ch",
        measure: "720px", // reading measure: knowledge, skill bodies
        form: "960px", // forms and settings content
        content: "72rem", // a workbench page
        empty: "360px",
      },
    },
  },
  plugins: [animate],
};
