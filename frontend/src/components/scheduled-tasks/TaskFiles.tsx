// src/components/scheduled-tasks/TaskFiles.tsx — an open task's Files tab: the task's own folder, read-only.
//
// The same Files card a skill's folder is browsed in (SkillFileSplit, canvas
// 4.3.01): the tree on the left, the open file on the right. The folder holds
// the task's PROMPT.md and, for a task that names no directory, whatever its
// runs wrote there — a daily report, a CSV. Files are changed on disk; Reveal
// in Finder opens the folder.
import { useState } from "react";

import { ReadOnlyFile } from "@/components/files/ReadOnlyFile";
import { SkillFileSplit } from "@/components/skills/SkillFileSplit";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { useScheduledTaskFileContent, useScheduledTaskFiles } from "@/lib/hooks/useScheduledTasks";

const PROMPT_FILE = "PROMPT.md";

function OpenFile({ uid, name, path }: { uid: string; name: string; path: string }) {
  const content = useScheduledTaskFileContent(uid, path);
  return <ReadOnlyFile path={path} displayPath={`${name}/${path}`} query={content} reveal />;
}

export function TaskFiles({ task }: { task: ScheduledTask }) {
  const tree = useScheduledTaskFiles(task.uid);
  const [selected, setSelected] = useState(PROMPT_FILE);
  return (
    <SkillFileSplit
      name={task.name}
      tree={tree}
      selected={selected}
      onSelect={setSelected}
      folderPath={task.folder}
      detail={<OpenFile key={selected} uid={task.uid} name={task.name} path={selected} />}
    />
  );
}
