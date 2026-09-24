import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Input, type InputProps } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// A masked text input with an eye toggle that reveals the value, so the user
// can verify a secret they typed (App Secret, tokens, …).
// Drop-in replacement for `<Input type="password" />`: forwards the ref and
// spreads all input props; the `type` prop is ignored (it owns masking).
export interface PasswordInputProps extends Omit<InputProps, "type"> {
  /** Class for the relative wrapper (e.g. `flex-1` inside a flex row). */
  containerClassName?: string;
}

const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ className, containerClassName, ...props }, ref) => {
    const { t } = useTranslation();
    const [visible, setVisible] = React.useState(false);
    const toggleLabel = visible ? t("common.hidePassword") : t("common.showPassword");
    return (
      <div className={cn("relative", containerClassName)}>
        <Input
          ref={ref}
          type={visible ? "text" : "password"}
          // Room for the toggle so a long value never slides under the icon.
          className={cn("pr-10", className)}
          {...props}
        />
        {/* A local provider so the toggle's tooltip also works in dialogs and
            tests rendered outside the app shell; nesting inside Layout's
            provider is harmless. */}
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => setVisible((v) => !v)}
                aria-label={toggleLabel}
                aria-pressed={visible}
                tabIndex={-1}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </TooltipTrigger>
            <TooltipContent>{toggleLabel}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    );
  },
);
PasswordInput.displayName = "PasswordInput";

export { PasswordInput };
