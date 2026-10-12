## Why

The custom tool editor squeezed testing into a side column, so a JSON body, a long URL and the response all wrapped in half the drawer; the description box was a few lines; the request's headers were an inherited list above an unaligned editable list; the body template was a plain text box, often one long imported line; and in Chinese the **Arguments** tab and the **Query** field were both "参数". A group's Overview stacked five sections and showed each environment as one line. The decisions and the options are in ADRs [A Custom Tool's Test and a Group's Environments Each Have Their Own Tab](../../../../docs/decisions/custom-tool-pages-give-testing-and-environments-their-own-tabs.md), [What an Agent Fills in a Custom Tool Is an Input](../../../../docs/decisions/what-an-agent-fills-in-a-custom-tool-is-an-input.md) and [A Body Template Is Laid Out by Its Tokens](../../../../docs/decisions/a-body-template-is-laid-out-by-its-tokens.md).

## What Changes

- The editor's tabs are General, Request, Inputs, Response and Test, full width; Test shows sample values and Run, the request to send (URL, headers with their source, the filled body), then the response with Body / Response headers tabs, and keeps its state across tabs.
- Arguments are called inputs in the UI and docs; Query becomes Query parameters (URL 查询参数) with a "Filled by" column naming the input.
- Every header list is one shared table (name, value, source).
- The body template is a code editor with holes marked, laid out on open when it is one line, with Format and a line-and-column error.
- Descriptions grow with their text.
- A group's tabs are Overview, Tools and Environments (`/custom-tools/<group>/environments`); each environment is a card showing everything it holds, with Edit and ⋯ Delete.
- The tools table shows a coloured method chip; Edit group has Basics and Judging the answer sections; the environment dialog is wider with column heads.

## Impact

- Specs: web-ui ("Manage custom tool groups on their own page", "Preview and test a custom tool in one chosen environment").
- Code: frontend only — custom-tools components, `lib/customTools/bodyTemplate.ts`, `sentRequest.ts`, `CodeEditor`, `Textarea` auto-grow, `TabsContent` hides inactive panels.
- Docs: guides (custom tools) en + zh; canvases Capabilities, Foundations.
