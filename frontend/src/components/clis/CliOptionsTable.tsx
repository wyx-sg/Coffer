// src/components/clis/CliOptionsTable.tsx — a command's options: every spelling, the value it takes, what it does, its default.
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { TruncatedText } from "@/components/ui/truncated-text";
import type { CliHelpOption } from "@/lib/api/clis";

interface Props {
  options: readonly CliHelpOption[];
}

export function CliOptionsTable({ options }: Props) {
  const { t } = useTranslation();
  const columns: Column<CliHelpOption>[] = [
    {
      key: "names",
      header: t("clis.commands.cols.option"),
      className: "w-[34%]",
      cell: (o) => (
        <span className="flex min-w-0 items-center gap-1.5">
          <TruncatedText
            mono
            className="text-xs"
            text={[o.names.join(", "), o.metavar].filter(Boolean).join(" ")}
          />
          {o.required ? <Badge variant="secondary">{t("clis.commands.required")}</Badge> : null}
        </span>
      ),
    },
    {
      key: "description",
      header: t("clis.commands.cols.description"),
      cell: (o) =>
        o.description ? <TruncatedText text={o.description} className="text-xs" /> : "—",
    },
    {
      key: "default",
      header: t("clis.commands.cols.default"),
      className: "w-[18%]",
      cell: (o) => (o.default ? <TruncatedText mono text={o.default} className="text-xs" /> : "—"),
    },
  ];
  return (
    <DataTable
      fixed
      pageSize={1000}
      rows={[...options]}
      columns={columns}
      rowKey={(o) => o.names.join(",")}
      emptyMessage={t("clis.commands.noOptions")}
    />
  );
}
