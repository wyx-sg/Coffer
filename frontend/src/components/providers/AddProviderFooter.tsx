// src/components/providers/AddProviderFooter.tsx — the Add dialog's footer: step 1 (Test or Detect again · Cancel · Next: Models), step 2 (Back · Cancel · Add provider).
import { Plug, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";

interface Props {
  step: 1 | 2;
  /** The local-runtime path: Detect again takes the place of Test. */
  local: boolean;
  detecting: boolean;
  testing: boolean;
  /** A Test has answered (the button then reads "Test again"). */
  tested: boolean;
  /** Local with no runtime chosen and no address typed: nothing to go on with. */
  nothingToAdd: boolean;
  adding: boolean;
  onDetect: () => void;
  onTest: () => void;
  onNext: () => void;
  onBack: () => void;
  onAdd: () => void;
  onClose: () => void;
}

export function AddProviderFooter({
  step,
  local,
  detecting,
  testing,
  tested,
  nothingToAdd,
  adding,
  onDetect,
  onTest,
  onNext,
  onBack,
  onAdd,
  onClose,
}: Props) {
  const { t } = useTranslation();
  const cancel = (
    <Button type="button" variant="ghost" onClick={onClose}>
      {t("common.cancel")}
    </Button>
  );
  if (step === 2) {
    return (
      <DialogFooter>
        <Button type="button" variant="outline" className="sm:mr-auto" onClick={onBack}>
          {t("providers.add.back")}
        </Button>
        {cancel}
        <Button type="button" onClick={onAdd} disabled={adding}>
          {t("providers.add.submit")}
        </Button>
      </DialogFooter>
    );
  }
  return (
    <DialogFooter>
      {local ? (
        <Button
          type="button"
          variant="outline"
          className="sm:mr-auto"
          disabled={detecting}
          onClick={onDetect}
        >
          <RefreshCw aria-hidden /> {t("providers.add.local.detectAgain")}
        </Button>
      ) : (
        <Button
          type="button"
          variant="outline"
          className="sm:mr-auto"
          disabled={testing}
          onClick={onTest}
        >
          <Plug aria-hidden /> {tested ? t("providers.test.again") : t("providers.actions.test")}
        </Button>
      )}
      {cancel}
      <Button type="button" onClick={onNext} disabled={testing || nothingToAdd}>
        {t("providers.add.next")}
      </Button>
    </DialogFooter>
  );
}
