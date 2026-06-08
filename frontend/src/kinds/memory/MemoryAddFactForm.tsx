// frontend/src/kinds/memory/MemoryAddFactForm.tsx
//
// Add-fact form: name / type / description / body inputs. Facts are written
// directly (no LLM at write time). All field state lives in the page; this
// component renders the form and forwards changes + submit.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  text: string;
  name: string;
  description: string;
  type: string;
  error: unknown;
  isPending: boolean;
  onTextChange: (value: string) => void;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onTypeChange: (value: string) => void;
  onSubmit: () => void;
}

export function MemoryAddFactForm({
  text,
  name,
  description,
  type,
  error,
  isPending,
  onTextChange,
  onNameChange,
  onDescriptionChange,
  onTypeChange,
  onSubmit,
}: Props) {
  const { t } = useTranslation();
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-medium">{t("memory.detail.addFact")}</h2>
      <form
        className="space-y-3 rounded-md border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) onSubmit();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="fact-name">{t("memory.detail.factName")}</Label>
            <Input
              id="fact-name"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              placeholder={t("memory.detail.factNamePlaceholder")}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="fact-type">{t("memory.detail.factType")}</Label>
            <Input
              id="fact-type"
              value={type}
              onChange={(e) => onTypeChange(e.target.value)}
              placeholder="project | reference | user | …"
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="fact-description">{t("memory.detail.factDescription")}</Label>
          <Input
            id="fact-description"
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="fact-body">{t("memory.detail.factBody")}</Label>
          <textarea
            id="fact-body"
            className="min-h-24 w-full rounded-md border border-input bg-background p-2 text-sm"
            value={text}
            onChange={(e) => onTextChange(e.target.value)}
            placeholder={t("memory.detail.factBodyPlaceholder")}
          />
        </div>
        {error ? <p className="text-sm text-destructive">{translateApiError(t, error)}</p> : null}
        <div className="flex justify-end">
          <Button type="submit" disabled={!text.trim() || isPending}>
            {isPending ? t("common.saving") : t("memory.detail.addFact")}
          </Button>
        </div>
      </form>
    </section>
  );
}
