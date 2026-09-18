// frontend/src/lib/hooks/useWorkflowTemplates.ts — the template surface's
// queries and mutations (spec workflow, FR-054/FR-056).
//
// A template is a Resource of kind `workflow` and nothing else (FR-001), so
// every read and every write here goes through the kind-agnostic resource
// endpoint every other client uses. There is no template route in the workflow
// contract, and this file must not grow one: a second write path would be a
// second contract for the same data (FR-056).
//
// None of the three mutations toasts its failure. Each caller renders it where
// it belongs instead — the editor against the field the refusal names
// (FR-055), the create dialog and the delete confirmation inline — and a toast
// would surface the same refusal twice, the second time without the field.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, throwApiError } from "@/lib/api/errors";
import { getApiClient } from "@/lib/api/client";
import { resourceKey, resourcesKey } from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";
import { WORKFLOW_TEMPLATE_KIND, type TemplateConfig } from "@/lib/api/workflow";
import { useResources } from "@/lib/hooks/useResources";

/** One registered template, as the list and the editor read it. */
export interface WorkflowTemplate {
  name: string;
  description: string | null;
  enabled: boolean;
  config: TemplateConfig;
}

function asTemplate(resource: {
  name: string;
  description?: string | null;
  enabled: boolean;
  config: Record<string, unknown>;
}): WorkflowTemplate {
  return {
    name: resource.name,
    description: resource.description ?? null,
    enabled: resource.enabled,
    // The row carries the template config verbatim — what was stored is what
    // the developer wrote (the kind validates it, it does not rewrite it).
    config: resource.config as unknown as TemplateConfig,
  };
}

/** Every registered template, for the list page. */
export function useWorkflowTemplates() {
  const query = useResources(WORKFLOW_TEMPLATE_KIND);
  return { ...query, templates: (query.data ?? []).map(asTemplate) };
}

/** One template, for the editor. */
export function useWorkflowTemplate(name: string) {
  return useQuery({
    queryKey: resourceKey(WORKFLOW_TEMPLATE_KIND, name),
    enabled: name.length > 0,
    queryFn: async (): Promise<WorkflowTemplate> => {
      const { data, error } = await getApiClient().GET("/resources/{kind}/{name}", {
        params: { path: { kind: WORKFLOW_TEMPLATE_KIND, name } },
      });
      if (error) throwApiError(error, "RESOURCE_NOT_FOUND", "template not found");
      if (!data) throw new ApiError("RESOURCE_NOT_FOUND", "empty template response");
      return asTemplate(data);
    },
  });
}

function useInvalidateTemplates() {
  const qc = useQueryClient();
  return (name?: string) => {
    void qc.invalidateQueries({ queryKey: resourcesKey });
    if (name !== undefined)
      void qc.invalidateQueries({ queryKey: resourceKey(WORKFLOW_TEMPLATE_KIND, name) });
  };
}

interface CreateInput {
  name: string;
  description: string | null;
  config: TemplateConfig;
}

/** Register a new template. */
export function useCreateWorkflowTemplate() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: ({ name, description, config }: CreateInput) =>
      resourcesApi.create({
        kind: WORKFLOW_TEMPLATE_KIND,
        name,
        description,
        config: config as unknown as Record<string, unknown>,
      }),
    onSuccess: (_data, { name }) => invalidate(name),
  });
}

interface SaveInput {
  name: string;
  description: string | null;
  config: TemplateConfig;
}

/** Save an edited template through `PATCH /resources/workflow/{name}`. */
export function useSaveWorkflowTemplate() {
  const qc = useQueryClient();
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: ({ name, description, config }: SaveInput) =>
      resourcesApi.update(WORKFLOW_TEMPLATE_KIND, name, {
        description,
        config: config as unknown as Record<string, unknown>,
      }),
    onSuccess: (_data, { name, description, config }) => {
      // Write what was just stored into the cache BEFORE invalidating.
      //
      // The editor has no draft: each edit is applied to whatever the cache
      // holds and written straight back (FR-062). Invalidating alone starts a
      // refetch, and until it lands the cache still holds the PREVIOUS
      // config — so a second edit made in that window would be computed from
      // it and would undo the first. Reordering two stages quickly did
      // exactly that. The refetch still runs and still wins; this only makes
      // the gap hold the right answer.
      qc.setQueryData<WorkflowTemplate>(resourceKey(WORKFLOW_TEMPLATE_KIND, name), (current) =>
        current === undefined ? current : { ...current, description, config },
      );
      invalidate(name);
    },
  });
}

interface RenameInput extends SaveInput {
  /** The new name. Equal to `name` means only the description changed. */
  newName: string;
}

/** Rename a workflow and rewrite its description in one PATCH.
 *
 *  The description is written into the config as well as onto the resource,
 *  because the page reads the config's (it is the one the editor maintains).
 *  The daemon applies the config first and the name last, so a refused config
 *  leaves the workflow where the caller can retry against it. */
export function useRenameWorkflowTemplate() {
  const invalidate = useInvalidateTemplates();
  const mutation = useMutation({
    mutationFn: ({ name, newName, description, config }: RenameInput) =>
      resourcesApi.update(WORKFLOW_TEMPLATE_KIND, name, {
        name: newName,
        description,
        config: { ...config, description: description || undefined } as unknown as Record<
          string,
          unknown
        >,
      }),
    // Both names: the old key must stop serving a workflow that is no longer
    // there, and the new one has nothing cached yet.
    onSuccess: (_data, { name, newName }) => {
      invalidate(name);
      if (newName !== name) invalidate(newName);
    },
  });
  return mutation;
}

/** Delete a template. A run froze its snapshot at creation, so this cannot
 *  strand one — `template_ref` is left dangling by design. */
export function useDeleteWorkflowTemplate() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: (name: string) => resourcesApi.remove(WORKFLOW_TEMPLATE_KIND, name),
    onSuccess: () => invalidate(),
  });
}
