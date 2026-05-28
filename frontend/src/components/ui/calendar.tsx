import "react-day-picker/style.css";
import * as React from "react";
import { DayPicker } from "react-day-picker";
import { zhCN } from "react-day-picker/locale";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

/**
 * react-day-picker bound to the Coffer theme. v10 styles entirely through
 * CSS custom properties, so we keep the library's default stylesheet and
 * only remap its `--rdp-*` variables onto the project's design tokens —
 * no fragile per-element classNames mapping to drift across versions.
 */
const THEME_VARS = {
  "--rdp-accent-color": "hsl(var(--primary))",
  "--rdp-accent-background-color": "hsl(var(--accent))",
  "--rdp-day-width": "2.25rem",
  "--rdp-day-height": "2.25rem",
  "--rdp-day_button-width": "2.25rem",
  "--rdp-day_button-height": "2.25rem",
  "--rdp-day_button-border-radius": "var(--radius)",
  "--rdp-selected-border": "2px solid hsl(var(--primary))",
  "--rdp-today-color": "hsl(var(--primary))",
  "--rdp-range_start-color": "hsl(var(--primary-foreground))",
  "--rdp-range_end-color": "hsl(var(--primary-foreground))",
  "--rdp-range_middle-background-color": "hsl(var(--accent))",
  "--rdp-range_middle-color": "hsl(var(--accent-foreground))",
} as React.CSSProperties;

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

export function Calendar({ className, style, ...props }: CalendarProps) {
  // Month names and weekday headers follow the active UI language.
  const { i18n } = useTranslation();
  const locale = i18n.language.startsWith("zh") ? zhCN : undefined;
  return (
    <DayPicker
      locale={locale}
      className={cn("text-sm", className)}
      style={{ ...THEME_VARS, ...style }}
      {...props}
    />
  );
}
