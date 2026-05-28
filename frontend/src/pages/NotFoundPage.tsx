import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl tracking-tight">{t("notFound.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("notFound.subtitle", { path: pathname })}
        </p>
      </header>
      <Card className="paper-card">
        <CardHeader>
          <CardTitle className="font-serif text-lg">{t("notFound.bodyTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-foreground/80">
          <p>{t("notFound.body")}</p>
          <Button asChild variant="outline" size="sm">
            <Link to="/resources">
              <ArrowLeft className="mr-1 size-4" />
              {t("notFound.cta")}
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
