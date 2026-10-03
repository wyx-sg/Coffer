// frontend/src/components/PageFallback.tsx
// What a route shows while its code-split page is still downloading (the
// Suspense fallback router.tsx wraps every lazy page in). It shows nothing for
// the first 300ms (animate-appear), so a quick download never flashes it.
import { useTranslation } from "react-i18next";

export function PageFallback() {
  const { t } = useTranslation();
  return (
    <p role="status" className="animate-appear text-sm text-muted-foreground">
      {t("common.loading")}
    </p>
  );
}
