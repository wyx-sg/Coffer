// frontend/src/components/PageFallback.tsx
// What a route shows while its code-split page is still downloading (the
// Suspense fallback router.tsx wraps every lazy page in).
import { useTranslation } from "react-i18next";

export function PageFallback() {
  const { t } = useTranslation();
  return (
    <p role="status" className="text-sm text-muted-foreground">
      {t("common.loading")}
    </p>
  );
}
